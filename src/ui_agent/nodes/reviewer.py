"""4.8 render / audit / review nodes of the refine loop."""

from __future__ import annotations

import json
import re

from .. import mock, settings
from ..state import AgentState, ReviewResult
from ..llm import get_llm
from .common import design_snapshot, emit, image_block, rubric_text, run_dir, weighted_score
from .render import dom_summary, render_design

AUDIT_SEVERITY = {"A1": "high", "A2": "high", "A3": "high", "A4": "high", "A5": "medium", "A6": "medium",
                  "A7": "high", "A8": "medium"}
AUDIT_CRITERION = {"A1": "B5", "A2": "B4", "A3": "B5", "A4": "B5", "A5": "B3", "A6": "B6", "A7": "B8", "A8": "B6"}
AUDIT_EXPLANATION = {
    "A1": "Some visitors use screen readers or keyboards. These problems block them from using parts of the page.",
    "A2": "Low-contrast text is hard to read in sunlight, on cheap screens and for people with weaker eyesight.",
    "A3": "Sideways scrolling on a phone makes the page feel broken and hides content off-screen.",
    "A4": "Small buttons and links are easy to mis-tap on a phone, which feels like the site is broken.",
    "A5": "Very small text is tiring or impossible to read for many people, especially on phones.",
    "A6": "Errors and missing basics can break the page in some browsers and confuse the next developer.",
    "A7": "Keyboard users need to see where they are. Without a visible focus ring they get lost.",
    "A8": "The next developer rebuilds the page from these tokens and labels. Hard-coded values get lost or drift.",
}


async def render_node(state: AgentState) -> dict:
    cur = state["current"]
    emit("render_started", version=cur["version"])
    design, render = await render_design(state["run_id"], cur, f"refine/v{cur['version']}-shots")
    return {"current": design}


async def audit_node(state: AgentState) -> dict:
    # The audit itself ran with the render (same browser session); this node reports it.
    cur = state["current"]
    audit = cur.get("audit") or {}
    emit("audit", version=cur["version"], passed=audit.get("passed"),
         checks=[{"id": c["id"], "name": c["name"], "passed": c["passed"], "details": c["details"]} for c in audit.get("checks", [])])
    return {}


def _review_content(state: AgentState, cur: dict) -> list:
    root = run_dir(state["run_id"])
    content: list = []
    for vp, width in (("desktop", 1440), ("mobile", 375), ("tablet", 768)):
        tiles = (cur.get("tiles") or {}).get(vp, [])
        for i, t in enumerate(tiles):
            content.append({"type": "text", "text": f"{vp} ({width}px wide), screen {i + 1} of {len(tiles)}:"})
            content.append(image_block(root / t))
    facts = json.loads((root / f"refine/v{cur['version']}-shots/render.json").read_text())
    audit = cur.get("audit") or {}
    previous = [{k: i[k] for k in ("id", "criterion", "severity", "selector", "evidence", "status")}
                for i in state.get("issues") or []]
    content.append({"type": "text", "text": "\n\n".join([
        f"<request>\n{state['prompt']}\n</request>",
        f"<page>\n{json.dumps(state['intake'], indent=1)}\n</page>",
        f"<style_spec>\n{json.dumps(state.get('style_lock'), indent=1)}\n</style_spec>",
        f"<audit passed=\"{audit.get('passed')}\">\n{json.dumps([c for c in audit.get('checks', []) if not c['passed']], indent=1)}\n</audit>",
        f"<dom_summary>\n{json.dumps(dom_summary(facts), indent=1)[:30000]}\n</dom_summary>",
        f"<previously_raised_issues>\n{json.dumps(previous, indent=1)}\n</previously_raised_issues>",
    ])})
    return content


def merge_issues(previous: list[dict], new: list[dict], audit: dict) -> list[dict]:
    prev = {i["id"]: i for i in previous}
    merged: dict[str, dict] = {}
    for i in new:
        old = prev.get(i["id"])
        if old and old["status"] == "resolved" and i["status"] == "open":
            i = {**i, "status": "regressed"}
        if old and old["id"].startswith("chg_"):
            i = {**old, "status": i["status"]}
        merged[i["id"]] = i
    for pid, p in prev.items():
        merged.setdefault(pid, p)  # not mentioned → keep last known status
    # Code-side guarantee: every failing audit check is covered by an open issue.
    open_text = " ".join(f"{i['id']} {i['evidence']}" for i in merged.values() if i["status"] != "resolved")
    for c in audit.get("checks", []):
        if c["passed"]:
            continue
        iid = f"iss_audit_{c['id'].lower()}"
        covered = re.search(rf"\b{c['id']}\b", open_text) is not None
        if covered or (iid in merged and merged[iid]["status"] != "resolved"):
            continue
        merged[iid] = {
            "id": iid, "criterion": AUDIT_CRITERION[c["id"]], "severity": AUDIT_SEVERITY[c["id"]],
            "selector": "body", "viewport": "all",
            "evidence": f"{c['id']} {c['name']}: {c['details']}. {json.dumps(c['items'])[:500]}",
            "suggested_fix": "Fix every item listed in the evidence.", "explanation": AUDIT_EXPLANATION[c["id"]],
            "status": "open",
        }
    # Audit-backed issues that now pass are resolved by definition.
    passing = {c["id"].lower() for c in audit.get("checks", []) if c["passed"]}
    for iid, i in merged.items():
        if iid.startswith("iss_audit_") and iid.removeprefix("iss_audit_") in passing:
            merged[iid] = {**i, "status": "resolved"}
    return list(merged.values())


async def review(state: AgentState) -> dict:
    cur = state["current"]
    root = run_dir(state["run_id"])
    emit("review_started", version=cur["version"])
    system = settings.prompt("reviewer").replace("{rubric}", rubric_text())
    result, usage = await get_llm().parse(
        "reviewer", system=system, content=_review_content(state, cur), output_format=ReviewResult,
        mock=lambda: mock.review((root / cur["html_path"]).read_text(), cur.get("audit") or {},
                                 state.get("issues") or [], [i for i in state.get("issues") or [] if i["id"].startswith("chg_")]),
    )
    scores = {s.criterion: s.model_dump() for s in result.scores}
    for c in settings.rubric()["layer_b"]:
        scores.setdefault(c["id"], {"criterion": c["id"], "score": 3, "evidence": "Not scored by the reviewer."})
    for s in scores.values():
        s["score"] = max(1, min(5, int(s["score"])))
    score_list = sorted(scores.values(), key=lambda s: s["criterion"])
    issues = merge_issues(state.get("issues") or [], [i.model_dump() for i in result.issues], cur.get("audit") or {})
    score = weighted_score(score_list)
    review_d = {"summary": result.summary, "scores": score_list, "issues": issues}
    design = {**cur, "review": review_d, "score": score}
    (root / "refine" / f"v{cur['version']}-review.json").write_text(json.dumps(review_d, indent=2))
    iteration = (state.get("iteration") or 0) + 1
    snap = design_snapshot(design)
    emit("iteration", iteration=iteration, snapshot=snap)
    return {
        "current": design, "issues": issues, "iteration": iteration, "history": [snap], "usage": usage,
        "resolved_issue_ids": [i["id"] for i in issues if i["status"] == "resolved"],
    }
