"""Planner composition and diversity, sketch kit, gate decisions, sandboxed editor, color repair, tokens export."""

from pathlib import Path

from ui_agent import mock
from ui_agent.color import check_palette, repair_palette
from ui_agent.nodes.gate import gate
from ui_agent.nodes.handoff import w3c_tokens
from ui_agent.nodes.planner import diversity_problems, slots_for
from ui_agent.nodes.sketch import with_kit
from ui_agent.nodes.reviewer import merge_issues
from ui_agent.tools.text_editor import TextEditor


def test_slots_composition():
    assert slots_for(1, False) == ["neutral"]
    assert slots_for(2, True) == ["taste", "neutral"]
    s = slots_for(5, True)
    assert s.count("wildcard") == 1 and s.count("taste") == 2
    assert slots_for(3, False) == ["neutral", "neutral", "wildcard"]
    assert slots_for(10, True).count("taste") == 4


def test_diversity_check_flags_identical_briefs():
    intake = {"sections": ["hero", "features", "testimonials", "cta", "footer"]}
    b = mock.plan(3, intake, ["neutral", "neutral", "wildcard"]).briefs
    assert not diversity_problems(b)
    b[1] = b[0].model_copy(update={"id": "b"})
    assert diversity_problems(b)


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
