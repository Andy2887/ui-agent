"""4.5 render_and_audit_all, 4.6 gallery (interrupt #1)."""

from __future__ import annotations

from typing import Literal

from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt

from ..memory import store as memory
from ..state import AgentState, usage_reducer
from .common import emit
from .executor import apply_fixes
from .render import render_design


def _broken(design: dict, sections: list[str]) -> list[dict]:
    """Issues that make a candidate unfit for the gallery: overflow or missing sections."""
    issues = []
    checks = {c["id"]: c for c in (design.get("audit") or {}).get("checks", [])}
    if "A3" in checks and not checks["A3"]["passed"]:
        issues.append({"id": "iss_horizontal_overflow", "criterion": "B5", "severity": "high", "selector": "body",
                       "viewport": "mobile", "evidence": checks["A3"]["details"] + f" {checks['A3']['items']}"[:600],
                       "suggested_fix": "Constrain the overflowing elements (max-width: 100%, min-width: 0 on grid/flex children, wrap long lines).",
                       "explanation": "Sideways scrolling on a phone makes a page feel broken.", "status": "open"})
    return issues


async def render_and_audit_all(state: AgentState) -> dict:
    sections = state["intake"]["sections"]
    repaired = []
    usage: dict = {}
    for d in state.get("candidates") or []:
        if d.get("error"):
            repaired.append(d)
            continue
        problems = _broken(d, sections)
        if problems:
            emit("candidate_repair", id=d["direction_id"], problems=[p["id"] for p in problems])
            try:
                dst = f"candidates/{d['direction_id']}/v1-repaired.html"
                _, u, _ = await apply_fixes(state["run_id"], d["html_path"], dst, problems, style_spec=None, do_not_regress=[])
                usage = usage_reducer(usage, u)
                d, _ = await render_design(state["run_id"], {**d, "html_path": dst}, f"candidates/{d['direction_id']}/shots-repaired")
                emit("candidate_ready", id=d["direction_id"], design=d, brief=next(b for b in state["briefs"] if b["id"] == d["direction_id"]))
            except Exception as e:  # keep the original if repair fails
                d = {**d, "repair_error": str(e)}
        repaired.append(d)
    order = {b["id"]: i for i, b in enumerate(state["briefs"])}
    repaired.sort(key=lambda d: order.get(d["direction_id"], 99))
    return {"candidates": [{"__reset__": True}] + repaired, "usage": usage}


async def gallery(state: AgentState, *, store: BaseStore) -> Command[Literal["lock_style", "plan_directions"]]:
    briefs = {b["id"]: b for b in state["briefs"]}
    payload = {
        "kind": "gallery",
        "candidates": [
            {"id": d["direction_id"], "name": briefs[d["direction_id"]]["name"],
             "description": briefs[d["direction_id"]]["description"], "slot": briefs[d["direction_id"]]["slot"],
             "html_path": d["html_path"], "screenshots": d.get("screenshots", {}), "error": d.get("error"),
             "audit": [{"id": c["id"], "name": c["name"], "passed": c["passed"], "details": c["details"]}
                       for c in (d.get("audit") or {}).get("checks", [])],
             "brief": briefs[d["direction_id"]]}
            for d in state["candidates"]
        ],
        "preferences": state["preferences"],
        "candidate_count": state["candidate_count"],
    }
    answer = interrupt(payload)

    if answer.get("action") == "regenerate":
        update = {"regenerate_feedback": answer.get("feedback") or "Try clearly different directions."}
        if answer.get("preferences"):
            update["preferences"] = answer["preferences"]
        if answer.get("candidate_count"):
            update["candidate_count"] = max(1, min(10, int(answer["candidate_count"])))
        emit("regenerating", feedback=update["regenerate_feedback"])
        return Command(goto="plan_directions", update=update)

    pick = answer["id"]
    if pick not in briefs:
        raise ValueError(f"unknown candidate {pick!r}")
    notes = (answer.get("notes") or "").strip()
    rejected = [b for k, b in briefs.items() if k != pick]
    await memory.record_pick(store, state["user_id"], briefs[pick], rejected, notes)
    emit("picked", id=pick, notes=notes)
    return Command(goto="lock_style", update={"selection": {"id": pick, "notes": notes},
                                              "rejected_ids": [b["id"] for b in rejected]})
