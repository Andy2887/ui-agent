"""Site map and flow links, token locking, style spec, library sampling, sketch parsing, gate decisions, sandboxed
editor, color repair, tokens export."""

from pathlib import Path

from ui_agent import mock, settings
from ui_agent.color import check_palette, repair_palette
from ui_agent.nodes.gate import gate
from ui_agent.library import design_library, industry_priors, style_recipe
from ui_agent.nodes.handoff import w3c_tokens
from ui_agent.nodes.common import lock_tokens, root_tokens
from ui_agent.nodes.intake import plan_site
from ui_agent.nodes.sketch import extract_sketch, sketch_notation
from ui_agent.nodes.style_lock import style_spec
from ui_agent.nodes.reviewer import merge_issues
from ui_agent.tools.autofix import apply_font_floor
from ui_agent.state import MAX_PAGES, FlowPlan, FlowStep, IntakeResult, PagePlan
from ui_agent.tools.checks.flow import a11_flow_links
from ui_agent.tools.checks.slop import a10_slop
from ui_agent.tools.text_editor import TextEditor


def _intake(pages, flows, **kw):
    return IntakeResult(product_name="Inkwell", product_category="newsletter platform", problem="p", audience="a",
                        user_needs=[], pages=[PagePlan(**{"page_type": "landing", "purpose": "x", "primary_action": "go",
                                                          "sections": [], "links_to": [], **pg}) for pg in pages],
                        flows=[FlowPlan(name=n, steps=[FlowStep(page=pg, action="a") for pg in st]) for n, st in flows],
                        assumptions=[], questions=[], **kw)


def test_site_map_puts_the_entry_page_first_and_links_every_flow_step():
    r = plan_site(_intake(
        [{"id": "Sign Up", "name": "Sign up", "page_type": "auth"}, {"id": "home", "name": "Home"},
         {"id": "post", "name": "Post", "page_type": "nonsense", "links_to": ["ghost", "post"]}],
        [("Reader subscribes", ["home", "post", "Sign Up"])]))
    assert [p.id for p in r.pages] == ["home", "sign-up", "post"]
    assert [p.file for p in r.pages] == ["index.html", "sign-up.html", "post.html"]
    links = {p.id: p.links_to for p in r.pages}
    assert links["home"] == ["post"] and links["post"] == ["sign-up"]  # unknown and self links dropped
    assert r.flows[0].steps[2].page == "sign-up"
    post = next(p for p in r.pages if p.id == "post")
    assert post.page_type == "landing" and post.sections and any("unknown page type" in a for a in r.assumptions)


def test_site_map_caps_pages_and_drops_their_steps():
    pages = [{"id": f"p{i}", "name": f"P{i}"} for i in range(MAX_PAGES + 2)]
    r = plan_site(_intake(pages, [("f", [f"p{i}" for i in range(MAX_PAGES + 2)])]))
    assert len(r.pages) == MAX_PAGES and r.not_designed == [f"P{MAX_PAGES}", f"P{MAX_PAGES + 1}"]
    assert len(r.flows[0].steps) == MAX_PAGES


def test_lock_tokens_keeps_extra_tokens_and_adds_missing_ones():
    html = "<style>:root { --color-bg: #fff; --color-text: #111; --only-here: 2px; } .a { color: var(--color-text); }</style>"
    out, changed = lock_tokens(html, {"--color-bg": "#000", "--color-text": "#111", "--space-1": "4px"})
    toks = root_tokens(out)
    assert toks == {"--color-bg": "#000", "--color-text": "#111", "--only-here": "2px", "--space-1": "4px"}
    assert changed == ["--color-bg", "--space-1"] and ".a { color: var(--color-text); }" in out
    assert lock_tokens(out, root_tokens(out)) == (out, [])


def test_style_spec_comes_from_the_direction_not_the_render():
    direction = {**mock.plan(plan_site(_intake([{"id": "home", "name": "Home"}], [])).model_dump(), "neutral").model_dump(),
                 "avoid": ["stock photos"]}
    spec = style_spec(direction, {"--color-bg": "#fff"}, "warmer copy")
    assert spec["signature_elements"] == [direction["signature_element"]]
    assert spec["tokens"] == {"--color-bg": "#fff"} and spec["user_notes"] == "warmer copy"
    assert "Avoid: stock photos" in spec["must_keep"] and direction["heading_font"] in spec["character"]


def test_parallel_pages_share_one_budget():
    from ui_agent import llm
    limit = float(settings.config()["budget_usd_per_run"])
    assert not llm.over_budget({"cost_usd": limit - 1})
    token = llm.start_branch("run-x", base_cost=limit - 1)
    try:
        assert not llm.over_budget({})  # a branch's own usage starts at zero; the shared counter is what counts
        llm._live_spend["run-x"] = 0.6  # spent by sibling pages
        assert not llm.over_budget({})
        llm._live_spend["run-x"] += 0.5
        assert llm.over_budget({})
    finally:
        llm.end_branch(token)
        llm.reset_live_spend("run-x")
    assert not llm.over_budget({"cost_usd": limit - 1})


def test_flow_links_check():
    links = {"required": ["post.html", "sign-up.html"], "known": ["index.html", "post.html", "sign-up.html"]}
    html = '<a href="./post.html">Read</a> <a href="https://x.com/a.html">x</a> <a href="#faq">FAQ</a> <a href="pricing.html">P</a>'
    c = a11_flow_links(html, links)
    assert not c.passed and c.items == [{"missing_link_to": "sign-up.html"}, {"link_to_unknown_page": "pricing.html"}]
    ok = a11_flow_links('<a href="post.html">a</a><form action="sign-up.html"></form>', links)
    assert ok.passed and a11_flow_links("", None) is None


def test_industry_priors_follow_the_product_category():
    brief = {"problem": "A city food bank cannot fill weekend sorting shifts.", "audience": "Local residents and students."}
    names = [p["name"] for p in industry_priors(brief, {"product_category": "non-profit food bank volunteering"})]
    assert names[0] == "Non-profit/Charity"
    clinic = industry_priors({"problem": "Patients phone to book.", "audience": "Adults with injuries."},
                             {"product_category": "physiotherapy clinic"})
    assert clinic[0]["name"] == "Medical Clinic" and clinic[0]["avoid"]


def test_library_sample_is_seeded_and_mixes_typical_with_random():
    brief = {"problem": "Patients phone to book.", "audience": "Adults with injuries."}
    intake = {"pages": [{"page_type": "landing"}], "product_category": "physiotherapy clinic"}
    priors = industry_priors(brief, intake)
    a = design_library(brief, intake, priors, seed="run-1")
    assert a == design_library(brief, intake, priors, seed="run-1")
    assert a != design_library(brief, intake, priors, seed="run-2")
    fits = {s["fit"] for s in a["reference_styles"]}
    assert fits == {"typical for products like this", "a less obvious option"}
    typical = {s["id"] for s in a["reference_styles"] if s["fit"].startswith("typical")}
    assert "accessible-and-ethical" in typical and "claymorphism" not in typical  # its avoid_for names medical
    assert all("landing" in settings.structure(s["id"])["page_types"] for s in a["page_structures"])


def test_style_recipe_reaches_the_designer():
    assert style_recipe("bento-box-grid")["recipe"]["css"]
    assert style_recipe(None) is None and style_recipe("not-a-style") is None


def test_sketch_is_extracted_from_fenced_output():
    sketch = "DESKTOP 1440px\n+-- hero --+\n\nMOBILE 375px\nhero: stacks\n\nNOTES\n(1) why\n"
    assert extract_sketch(f"Here it is:\n```\n{sketch}```\n") == sketch
    assert extract_sketch(sketch) == sketch
    assert "[[ Label ]]" in sketch_notation() and "## Rules" not in sketch_notation()


def test_color_repair_keeps_hue_and_reaches_aa():
    pal = {"bg": "#FFFFFF", "surface": "#FFFFFF", "text": "#999999", "muted": "#AAAAAA", "primary": "#FFB020",
           "on_primary": "#FFFFFF", "accent": "#FFE680", "border": "#EEEEEE"}
    fixed, notes = repair_palette(pal)
    assert not check_palette(fixed) and notes


def test_text_editor_is_sandboxed(tmp_path: Path):
    f = tmp_path / "v2.html"
    f.write_text("<p>a</p>\n<p>a</p>\n<p>b</p>")
    ed = TextEditor(f)
    assert not ed.handle({"command": "view", "path": "../../etc/passwd"})[0]
    assert not ed.handle({"command": "create", "path": "index.html", "file_text": "x"})[0]
    assert not ed.handle({"command": "str_replace", "path": "index.html", "old_str": "<p>a</p>", "new_str": "x"})[0]
    assert ed.handle({"command": "str_replace", "path": "index.html", "old_str": "<p>b</p>", "new_str": "<p>c</p>"})[0]
    assert "<p>c</p>" in f.read_text()


def _design(v, score, passed=True, scores=4):
    return {"version": v, "html_path": f"refine/v{v}.html", "score": score,
            "audit": {"passed": passed, "checks": [{"id": "A1", "passed": passed}]},
            "review": {"scores": [{"criterion": c, "score": scores} for c in ("B1", "B2")]}}


def test_gate_pass_revert_plateau_max():
    st = {"current": _design(1, 4.3), "iteration": 1, "iteration_cap": 5, "issues": [], "usage": {}}
    assert gate(st)["gate_decision"] == "pass"
    st = {"current": _design(1, 3.5, passed=False), "iteration": 1, "iteration_cap": 5, "issues": [], "usage": {}}
    assert gate(st)["gate_decision"] == "continue"
    st = {"current": _design(3, 3.0, False), "best": _design(2, 3.6, False), "iteration": 3, "iteration_cap": 5,
          "issues": [], "usage": {}, "best_scores": [3.6, 3.6]}
    out = gate(st)
    assert out["gate_decision"] == "revert" and out["current"]["version"] == 2
    st = {"current": _design(4, 3.62, False), "best": _design(3, 3.6, False), "iteration": 4, "iteration_cap": 5,
          "issues": [], "usage": {}, "best_scores": [3.55, 3.58, 3.6]}
    assert gate(st)["gate_decision"] == "plateau"
    st = {"current": _design(5, 3.9, False), "best": _design(4, 3.5, False), "iteration": 5, "iteration_cap": 5,
          "issues": [], "usage": {}, "best_scores": [3.0, 3.5]}
    out = gate(st)
    assert out["gate_decision"] == "max_iters" and out["stop_reason"] == "max_iters"


def test_open_high_issue_blocks_pass():
    issues = [{"id": "x", "severity": "high", "status": "open"}]
    st = {"current": _design(1, 4.6), "iteration": 1, "iteration_cap": 5, "issues": issues, "usage": {}}
    assert gate(st)["gate_decision"] == "continue"


def test_merge_issues_detects_regression_and_covers_audit():
    prev = [{"id": "iss_a", "criterion": "B1", "severity": "high", "selector": "s", "viewport": "all",
             "evidence": "e", "suggested_fix": "f", "explanation": "x", "status": "resolved"}]
    new = [{**prev[0], "status": "open"}]
    audit = {"checks": [{"id": "A3", "name": "Horizontal overflow", "passed": False, "details": "d", "items": []}]}
    merged = {i["id"]: i for i in merge_issues(prev, new, audit)}
    assert merged["iss_a"]["status"] == "regressed"
    assert merged["iss_audit_a3"]["status"] == "open"


def test_issue_covering_a_check_is_ranked_at_least_as_severe():
    low = {"id": "iss_hero_empty_right", "criterion": "B2", "severity": "low", "selector": "s", "viewport": "desktop",
           "evidence": "A9: the aside ends 345px above the copy", "suggested_fix": "f", "explanation": "x", "status": "open"}
    audit = {"checks": [{"id": "A9", "name": "Layout balance", "passed": False, "blocking": False, "details": "d", "items": []}]}
    merged = {i["id"]: i for i in merge_issues([], [low], audit)}
    assert merged["iss_hero_empty_right"]["severity"] == "medium" and "iss_audit_a9" not in merged


def test_slop_check_keeps_only_template_habits():
    findings = [{"antipattern": "hero-eyebrow-chip", "snippet": "eyebrow above h1"},
                {"antipattern": "icon-tile-stack", "snippet": "tile 1"}, {"antipattern": "icon-tile-stack", "snippet": "tile 2"},
                {"antipattern": "overused-font", "snippet": "Primary font: inter"},  # the direction owns its fonts
                {"antipattern": "low-contrast", "snippet": "4.0:1"}]  # A2's job
    c = a10_slop(findings)
    assert not c.passed and not c.blocking
    assert [(i["rule"], i["count"]) for i in c.items] == [("hero-eyebrow-chip", 1), ("icon-tile-stack", 2)]
    assert "overused-font" not in c.fix and c.fix.startswith("hero-eyebrow-chip:")
    assert a10_slop([{"antipattern": "overused-font"}]).passed
    skipped = a10_slop(None)
    assert skipped.passed and skipped.details.startswith("Skipped")


def test_audit_issue_carries_the_checks_own_fix():
    audit = {"checks": [a10_slop([{"antipattern": "side-tab", "snippet": "border-left: 4px"}]).model_dump()]}
    issue = {i["id"]: i for i in merge_issues([], [], audit)}["iss_audit_a10"]
    assert issue["criterion"] == "B10" and issue["severity"] == "medium" and "hairline" in issue["suggested_fix"]


def test_revert_restores_issue_statuses_of_best():
    # v2 fixes iss_a but scores lower and is reverted to v1. v3 is built on v1, so iss_a is
    # still there: that is "open", not a regression of a fix v1 never had.
    iss = {"id": "iss_a", "criterion": "B5", "severity": "high", "selector": "s", "viewport": "all",
           "evidence": "e", "suggested_fix": "f", "explanation": "x", "status": "open"}
    v1 = {**_design(1, 3.8, False), "review": {"scores": [], "issues": [iss]}}
    later = {**iss, "id": "iss_b", "status": "resolved"}
    st = {"current": _design(2, 3.3, False), "best": v1, "iteration": 2, "iteration_cap": 5,
          "issues": [{**iss, "status": "resolved"}, later], "usage": {}, "best_scores": [3.8]}
    out = gate(st)
    assert out["gate_decision"] == "revert"
    restored = {i["id"]: i["status"] for i in out["issues"]}
    assert restored == {"iss_a": "open", "iss_b": "open"}
    merged = {i["id"]: i for i in merge_issues(out["issues"], [{**iss, "status": "open"}], {"checks": []})}
    assert merged["iss_a"]["status"] == "open"
    st = {"current": _design(3, 3.75, False), "best": v1, "iteration": 3, "iteration_cap": 5,
          "issues": list(merged.values()), "usage": {}, "best_scores": [3.8]}
    assert gate(st)["gate_decision"] == "continue"


def test_w3c_tokens():
    t = w3c_tokens({"--color-bg": "#fff", "--font-heading": '"Inter", sans-serif', "--space-4": "16px", "--radius-md": "8px"})
    assert t["color"]["bg"] == {"$type": "color", "$value": "#fff"}
    assert t["fontFamily"]["heading"]["$type"] == "fontFamily"
    assert t["spacing"]["4"]["$value"] == "16px"


def test_font_floor_patches_the_rule_the_browser_found():
    html = ("<style data-base-layer>@layer base { p { font-size: 12px; } }</style>"
            "<style>.faq>p{color:red;font-size:.9375rem}\n[data-component=cta] .note { font-size: var(--fs-sm) !important; }"
            ".twice { font-size: 14px }\n@media (min-width: 768px) { .twice { font-size: 14px } }</style>")
    rules = [{"selector": ".faq > p", "value": "0.9375rem", "before": 15, "after": 16},
             {"selector": '[data-component="cta"] .note', "value": "var(--fs-sm)", "before": 15, "after": 16},
             {"selector": ".twice", "value": "14px", "before": 14, "after": 16}]
    out, applied = apply_font_floor(html, rules)
    assert ".faq>p{color:red;font-size: max(1rem, .9375rem)}" in out
    assert "font-size: max(1rem, var(--fs-sm)) !important;" in out
    assert out.count(".twice { font-size: 14px }") == 2  # found twice: ambiguous, left alone
    assert "@layer base { p { font-size: 12px; } }" in out  # the base layer is never patched
    assert [a["selector"] for a in applied] == [".faq > p", '[data-component="cta"] .note']

