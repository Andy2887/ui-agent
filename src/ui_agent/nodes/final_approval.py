"""4.9 final_approval (interrupt #2, optional)."""

from __future__ import annotations

from typing import Literal

from langgraph.types import Command, interrupt

from .. import settings
from ..state import AgentState
from .common import design_snapshot, emit


async def final_approval(state: AgentState) -> Command[Literal["build_handoff", "refine"]]:
    if not settings.config().get("final_approval", True):
        return Command(goto="build_handoff", update={"approved": True})
    best = state["best"]
    chosen = next(d for d in state["candidates"] if d["direction_id"] == state["selection"]["id"])
    payload = {
        "kind": "final_approval",
        "v1": {"version": 1, "html_path": chosen["html_path"], "screenshots": chosen.get("screenshots", {})},
        "final": design_snapshot(best),
        "trajectory": [{"version": h["version"], "score": h["score"],
                        "open_issues": sum(1 for i in h["issues"] if i["status"] in ("open", "regressed"))}
                       for h in state.get("history") or []],
        "remaining_issues": [i for i in state.get("issues") or [] if i["status"] in ("open", "regressed")],
        "stop_reason": state.get("stop_reason"),
        "usage": state.get("usage"),
    }
    answer = interrupt(payload)
    if answer.get("action") == "request_changes" and (answer.get("feedback") or "").strip():
        n = len(state.get("change_requests") or []) + 1
        cr = {"id": f"chg_{n}", "criterion": "B9", "severity": "high", "selector": "body", "viewport": "all",
              "evidence": f"Developer requested: {answer['feedback'].strip()}", "suggested_fix": answer["feedback"].strip(),
              "explanation": "You asked for this change at final review.", "status": "open"}
        cap = state.get("iteration", 0) + int(settings.config()["refine"]["change_request_max_iterations"])
        emit("changes_requested", request=cr)
        return Command(goto="refine", update={
            "issues": (state.get("issues") or []) + [cr],
            "change_requests": (state.get("change_requests") or []) + [cr],
            "change_requests_pending": True, "iteration_cap": cap, "stop_reason": None,
            "current": best, "gate_decision": None,
        })
    emit("approved")
    return Command(goto="build_handoff", update={"approved": True})
