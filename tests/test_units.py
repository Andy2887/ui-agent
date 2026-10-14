"""Planner composition and diversity, sketch kit, gate decisions, sandboxed editor, color repair, tokens export."""

from pathlib import Path

from ui_agent import mock, settings
from ui_agent.color import check_palette, repair_palette
from ui_agent.nodes.gate import gate
from ui_agent.library import design_library, industry_priors, style_recipe
from ui_agent.nodes.handoff import w3c_tokens
from ui_agent.nodes.planner import diversity_problems, slots_for
from ui_agent.nodes.sketch import with_kit
from ui_agent.nodes.reviewer import merge_issues
from ui_agent.tools.autofix import apply_font_floor
from ui_agent.tools.text_editor import TextEditor


def test_slots_composition():
    assert slots_for(1, False) == ["neutral"]
    assert slots_for(2, True) == ["taste", "neutral"]
    assert slots_for(2, False) == ["neutral", "bold"]
    s = slots_for(5, True)
    assert s == ["taste", "taste", "neutral", "bold", "wildcard"]
    assert slots_for(3, False) == ["neutral", "bold", "wildcard"]
    assert slots_for(10, True).count("taste") == 4
    for n in range(2, 11):
        s = slots_for(n, False)
        assert all(not (x == y == "neutral") for x, y in zip(s, s[1:])), s


def test_diversity_check_flags_identical_briefs():
    intake = {"sections": ["hero", "features", "testimonials", "cta", "footer"]}
    b = mock.plan(3, intake, ["neutral", "bold", "wildcard"]).briefs
    assert not diversity_problems(b)
    b[1] = b[0].model_copy(update={"id": "b"})
    assert diversity_problems(b)


def test_diversity_check_flags_shared_fonts_styles_and_variance():
    intake = {"sections": ["hero", "features", "testimonials", "cta", "footer"]}
    b = mock.plan(3, intake, ["neutral", "bold", "wildcard"]).briefs
    shared_font = [b[0], b[1].model_copy(update={"body_font": b[0].heading_font}), b[2]]
    assert any("both use" in p for p in diversity_problems(shared_font))
    same_style = [b[0], b[1].model_copy(update={"style_id": "editorial"}), b[2].model_copy(update={"style_id": "editorial"})]
    assert any("same library style" in p for p in diversity_problems(same_style))
    same_variance = [x.model_copy(update={"variance": "mid"}) for x in b]
    assert any("variance" in p for p in diversity_problems(same_variance))


def test_industry_priors_follow_the_product_category():
    brief = {"problem": "A city food bank cannot fill weekend sorting shifts.", "audience": "Local residents and students."}
    names = [p["name"] for p in industry_priors(brief, {"product_category": "non-profit food bank volunteering"})]
    assert names[0] == "Non-profit/Charity"
    clinic = industry_priors({"problem": "Patients phone to book.", "audience": "Adults with injuries."},
                             {"product_category": "physiotherapy clinic"})
    assert clinic[0]["name"] == "Medical Clinic" and clinic[0]["avoid"]


def test_library_sample_is_seeded_and_mixes_typical_with_random():
    brief = {"problem": "Patients phone to book.", "audience": "Adults with injuries."}
    intake = {"page_type": "landing", "product_category": "physiotherapy clinic"}
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


def test_sketch_kit_is_injected_once():
    html = "<!doctype html><html><head><title>x</title></head><body></body></html>"
    once = with_kit(html)
    assert once.count("data-sketch-kit") == 1 and once.index("data-sketch-kit") < once.index("<title>")
    assert with_kit(once).count("data-sketch-kit") == 1


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

