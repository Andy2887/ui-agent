"""4.10 final_approval (interrupt #3, optional): every page of the site, clickable, with its review. The PM approves,
or requests changes to one page or to all of them; those pages go back through their refine loops."""

from __future__ import annotations

from typing import Literal

from langgraph.types import Command, interrupt

from .. import settings
from ..state import AgentState
from .common import design_snapshot, emit


def page_summaries(state: AgentState) -> list[dict]:
    sketches = {s["page_id"]: s for s in state.get("sketches") or []}
    out = []
    for p in state["intake"]["pages"]:
        saved = (state.get("pages") or {}).get(p["id"]) or {}
        entry = {"id": p["id"], "name": p["name"], "file": p["file"], "purpose": p["purpose"],
                 "sketch": (sketches.get(p["id"]) or {}).get("text", ""), "skipped": saved.get("skipped")}
        if saved.get("best"):
            history = [h for h in state.get("history") or [] if h.get("page_id") == p["id"]]
            first = saved["design"]
            entry.update({
                "v1": {"version": 1, "html_path": first["html_path"], "screenshots": first.get("screenshots", {})},
                "final": design_snapshot(saved["best"]),
                "trajectory": [{"version": h["version"], "score": h["score"],
                                "open_issues": sum(1 for i in h["issues"] if i["status"] in ("open", "regressed"))}
                               for h in history],
                "remaining_issues": [i for i in saved.get("issues") or [] if i["status"] in ("open", "regressed")],
                "stop_reason": saved.get("stop_reason"),
            })
        out.append(entry)
    return out


async def final_approval(state: AgentState) -> Command[Literal["build_handoff", "next_pages"]]:
    if not settings.config().get("final_approval", True):
        return Command(goto="build_handoff", update={"approved": True})
    payload = {
        "kind": "final_approval",
        "pages": page_summaries(state),
        "flows": state["intake"].get("flows") or [],
        "not_designed": state["intake"].get("not_designed") or [],
        "site_dir": "site",
        "usage": state.get("usage"),
    }
    answer = interrupt(payload)
    feedback = (answer.get("feedback") or "").strip()
    if answer.get("action") == "request_changes" and feedback:
        ids = [p["id"] for p in state["intake"]["pages"]]
        target = answer.get("page_id") or "all"
        targets = ids if target == "all" else [target]
        if not set(targets) <= set(ids):
            raise ValueError(f"unknown page {target!r}")
        n = sum(len((state.get("pages") or {}).get(pid, {}).get("change_requests") or []) for pid in ids) + 1
        pending = {pid: [{"id": f"chg_{n}", "criterion": "B9", "severity": "high", "selector": "body", "viewport": "all",
                          "evidence": f"PM requested: {feedback}", "suggested_fix": feedback,
                          "explanation": "You asked for this change at final review.", "status": "open"}]
                   for pid in targets}
        emit("changes_requested", request=feedback, pages=targets)
        return Command(goto="next_pages", update={"pending_changes": pending, "page_queue": targets})
    emit("approved")
    return Command(goto="build_handoff", update={"approved": True})
