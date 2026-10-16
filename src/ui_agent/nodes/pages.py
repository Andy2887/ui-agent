"""4.6 sketch_review (interrupt #2): the PM approves the direction and every page's sketch, or asks for changes.
Then the page loop: next_page picks the page to design (or revisit), and finish_page saves it once refined."""

from __future__ import annotations

import shutil
from typing import Literal

from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt

from .. import settings
from ..memory import store as memory
from ..state import AgentState
from .common import emit, key_page_id, lock_tokens, page_spec, root_tokens, run_dir

# The refine loop's per-page keys, saved in state["pages"][page_id] when a page finishes.
PAGE_KEYS = ("design", "best", "issues", "change_requests", "resolved_issue_ids", "iteration", "iteration_cap",
             "best_scores", "stop_reason", "regression_note")


async def sketch_review(state: AgentState, *, store: BaseStore) -> Command[Literal["next_page", "plan_direction"]]:
    sketches = {s["page_id"]: s for s in state.get("sketches") or []}
    pages = state["intake"]["pages"]
    payload = {
        "kind": "sketch_review",
        "design_brief": {k: v for k, v in state["intake"].items() if k != "questions"},
        "direction": state["direction"],
        "pages": [{**p, "sketch": (sketches.get(p["id"]) or {}).get("text", ""), "error": (sketches.get(p["id"]) or {}).get("error")}
                  for p in pages],
    }
    answer = interrupt(payload)

    rejected = list(state.get("rejected_directions") or [])
    if answer.get("action") == "revise":
        feedback = (answer.get("feedback") or "").strip() or "Try a clearly different direction."
        emit("revising", feedback=feedback)
        return Command(goto="plan_direction", update={"revise_feedback": feedback,
                                                      "rejected_directions": rejected + [state["direction"]]})

    notes = (answer.get("notes") or "").strip()
    await memory.record_pick(store, state["user_id"], state["direction"], rejected, notes)
    emit("sketches_approved", notes=notes, pages=[p["id"] for p in pages])
    return Command(goto="next_page", update={
        "sketch_notes": notes, "page_queue": [p["id"] for p in pages], "pages": {}, "pending_changes": {},
        "style_lock": None, "change_requests": [],
    })


async def next_page(state: AgentState) -> Command[Literal["design_page", "refine", "final_approval"]]:
    queue = list(state.get("page_queue") or [])
    done = state.get("pages") or {}
    pending = dict(state.get("pending_changes") or {})
    total = len(state["intake"]["pages"])
    while queue:
        pid = queue.pop(0)
        changes = pending.pop(pid, [])
        saved = done.get(pid)
        index = [p["id"] for p in state["intake"]["pages"]].index(pid) + 1
        if saved is None or saved.get("skipped"):
            emit("page_started", page_id=pid, name=page_spec(state, pid)["name"], index=index, total=total)
            return Command(goto="design_page", update={"page_queue": queue, "pending_changes": pending,
                                                       "page_id": pid, "change_requests": changes})
        if changes:
            # Back into this page's refine loop, from its best version, with the PM's requests on top.
            restored = {k: saved.get(k) for k in PAGE_KEYS}
            cap = (saved.get("iteration") or 0) + int(settings.config()["refine"]["change_request_max_iterations"])
            emit("page_started", page_id=pid, name=page_spec(state, pid)["name"], index=index, total=total, revisit=True)
            return Command(goto="refine", update={
                **restored, "page_queue": queue, "pending_changes": pending, "page_id": pid,
                "issues": (saved.get("issues") or []) + changes,
                "change_requests": (saved.get("change_requests") or []) + changes,
                "change_requests_pending": True, "iteration_cap": cap, "stop_reason": None,
                "current": saved["best"], "gate_decision": None,
            })
    return Command(goto="final_approval", update={"page_queue": [], "pending_changes": {}})


async def finish_page(state: AgentState) -> dict:
    """Save the page's refine state, publish its best version to site/ (where the pages link to each other),
    and, for the key page, lock its final tokens for every page that follows."""
    pid = state["page_id"]
    best = state["best"]
    root = run_dir(state["run_id"])
    site = root / "site"
    site.mkdir(exist_ok=True)
    shutil.copyfile(root / best["html_path"], site / page_spec(state, pid)["file"])
    pages = {**(state.get("pages") or {}), pid: {"page_id": pid, **{k: state.get(k) for k in PAGE_KEYS}}}
    update: dict = {"pages": pages}
    if pid == key_page_id(state) and state.get("style_lock"):
        tokens = root_tokens((root / best["html_path"]).read_text())
        update["style_lock"] = {**state["style_lock"], "tokens": tokens}
        # A change request on the key page can move its tokens after other pages were done: keep them in step.
        for other, saved in pages.items():
            if other != pid and saved.get("best"):
                html, changed = lock_tokens((root / saved["best"]["html_path"]).read_text(), tokens)
                (site / page_spec(state, other)["file"]).write_text(html)
                if changed:
                    emit("tokens_locked", page_id=other, changed=changed)
    emit("page_done", page_id=pid, version=best["version"], score=best.get("score"), stop_reason=state.get("stop_reason"))
    return update
