"""4.6 gallery (interrupt #2): the PM picks one sketch, or asks for different directions."""

from __future__ import annotations

from typing import Literal

from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt

from ..memory import store as memory
from ..state import AgentState
from .common import emit


async def gallery(state: AgentState, *, store: BaseStore) -> Command[Literal["design", "plan_directions"]]:
    briefs = {b["id"]: b for b in state["briefs"]}
    order = {b["id"]: i for i, b in enumerate(state["briefs"])}
    sketches = sorted(state.get("candidates") or [], key=lambda d: order.get(d["direction_id"], 99))
    payload = {
        "kind": "gallery",
        "design_brief": {k: v for k, v in state["intake"].items() if k != "questions"},
        "candidates": [
            {"id": d["direction_id"], "name": briefs[d["direction_id"]]["name"],
             "description": briefs[d["direction_id"]]["description"], "slot": briefs[d["direction_id"]]["slot"],
             "html_path": d["html_path"], "screenshots": d.get("screenshots", {}), "error": d.get("error"),
             "brief": briefs[d["direction_id"]]}
            for d in sketches
        ],
        "candidate_count": state["candidate_count"],
    }
    answer = interrupt(payload)

    if answer.get("action") == "regenerate":
        update = {"regenerate_feedback": answer.get("feedback") or "Try clearly different directions."}
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
    return Command(goto="design", update={"selection": {"id": pick, "notes": notes},
                                          "rejected_ids": [b["id"] for b in rejected]})
