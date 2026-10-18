"""4.6 sketch_review (interrupt #2): the PM approves the direction and every page's sketch, or asks for changes.

Then the pages, in at most two parallel batches. The key page (the entry page of flow 1) goes alone, because every
other page is designed against its final HTML and tokens. Once it is done, every remaining page is designed and
refined at the same time, each in its own branch (build_page) with its own private refine state."""

from __future__ import annotations

import shutil
from typing import Literal

from langgraph.store.base import BaseStore
from langgraph.types import Command, Send, interrupt

from .. import settings
from ..llm import end_branch, reset_live_spend, start_branch
from ..memory import store as memory
from ..refine_graph import refine
from ..state import AgentState, usage_reducer
from .common import emit, key_page_id, lock_tokens, page_spec, root_tokens, run_dir
from .generator import design_page
from .style_lock import lock_style

# The refine loop's per-page keys, saved in state["pages"][page_id] when a page finishes.
PAGE_KEYS = ("design", "best", "issues", "change_requests", "resolved_issue_ids", "iteration", "iteration_cap",
             "best_scores", "stop_reason", "regression_note")
# What a page branch reads from the run's state. Everything else in its state is private to the branch.
BRANCH_KEYS = ("run_id", "user_id", "brief", "intake", "kickoff", "memory_context", "direction", "sketches",
               "sketch_notes", "style_lock", "pages")

async def sketch_review(state: AgentState, *, store: BaseStore) -> Command[Literal["next_pages", "plan_direction"]]:
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
    return Command(goto="next_pages", update={
        "sketch_notes": notes, "page_queue": [p["id"] for p in pages], "pending_changes": {},
        "style_lock": None, "change_requests": [],
    })


def page_batch(state: AgentState) -> list[str]:
    """The pages to run next: the key page alone while it is queued, then everything else at once."""
    queue = list(state.get("page_queue") or [])
    key = key_page_id(state)
    return [key] if key in queue else queue


async def next_pages(state: AgentState) -> dict:
    batch = page_batch(state)
    if batch:
        reset_live_spend(state["run_id"])
        emit("pages_started", pages=batch)
    return {}


def route_pages(state: AgentState) -> list[Send] | str:
    batch = page_batch(state)
    if not batch:
        return "final_approval"
    shared = {k: state.get(k) for k in BRANCH_KEYS}
    pending = state.get("pending_changes") or {}
    return [Send("build_page", {
        "state": shared, "page_id": pid, "changes": pending.get(pid) or [],
        "history": [h for h in state.get("history") or [] if h.get("page_id") == pid],  # for version numbers
        "base_cost": (state.get("usage") or {}).get("cost_usd", 0.0),
    }) for pid in batch]


def _apply(st: dict, update: dict) -> dict:
    """A node's update applied to a branch's private state, with the run state's reducers for usage and history."""
    out = {**st, **{k: v for k, v in update.items() if k not in ("usage", "history")}}
    out["usage"] = usage_reducer(st.get("usage"), update.get("usage"))
    out["history"] = (st.get("history") or []) + (update.get("history") or [])
    return out


async def build_page(payload: dict, config) -> dict:
    """One page, start to finish, in its own private state: design v1 and refine it, or, for a page with change
    requests from final review, go back into its refine loop from its best version. Returns only the page's
    record plus its history and usage, so parallel branches merge cleanly."""
    pid, changes = payload["page_id"], payload.get("changes") or []
    hist0 = len(payload.get("history") or [])
    st: dict = {**payload["state"], "page_id": pid, "usage": {}, "history": list(payload.get("history") or [])}
    saved = (st.get("pages") or {}).get(pid)
    revisit = bool(saved and not saved.get("skipped"))
    pages = st["intake"]["pages"]
    token = start_branch(st["run_id"], payload["base_cost"])
    try:
        emit("page_started", page_id=pid, name=page_spec(st, pid)["name"], index=[p["id"] for p in pages].index(pid) + 1,
             total=len(pages), revisit=revisit)
        if revisit:
            # Back into this page's refine loop, from its best version, with the PM's requests on top.
            cap = (saved.get("iteration") or 0) + int(settings.config()["refine"]["change_request_max_iterations"])
            st.update({k: saved.get(k) for k in PAGE_KEYS})
            st.update({"issues": (saved.get("issues") or []) + changes,
                       "change_requests": (saved.get("change_requests") or []) + changes,
                       "change_requests_pending": True, "iteration_cap": cap, "stop_reason": None,
                       "current": saved["best"], "gate_decision": None})
        else:
            st["change_requests"] = changes
            first = await design_page(st)
            if first is None:
                return {"pages": {pid: {"page_id": pid, "skipped": "budget"}}}
            st = _apply(st, first)
            st = _apply(st, await lock_style(st))
        st = _apply(st, await refine(st, config))
    finally:
        end_branch(token)

    best = st["best"]
    root = run_dir(st["run_id"])
    (root / "site").mkdir(exist_ok=True)
    shutil.copyfile(root / best["html_path"], root / "site" / page_spec(st, pid)["file"])
    out = {"pages": {pid: {"page_id": pid, **{k: st.get(k) for k in PAGE_KEYS}}},
           "history": st["history"][hist0:], "usage": st["usage"]}
    if pid == key_page_id(st):
        out["style_lock"] = st["style_lock"]  # only the key page ever runs alone, so no two branches write it
    emit("page_done", page_id=pid, version=best["version"], score=best.get("score"), stop_reason=st.get("stop_reason"))
    return out


async def collect_pages(state: AgentState) -> dict:
    """After a batch: take its pages off the queue and, once the key page is done, lock its final tokens for every
    page that follows. A change request on the key page can move its tokens after other pages were done, so their
    published copies are re-synced too."""
    batch = page_batch(state)
    reset_live_spend(state["run_id"])
    update: dict = {"page_queue": [p for p in state.get("page_queue") or [] if p not in batch],
                    "pending_changes": {k: v for k, v in (state.get("pending_changes") or {}).items() if k not in batch}}
    key = key_page_id(state)
    pages = state.get("pages") or {}
    if key in batch and (pages.get(key) or {}).get("best") and state.get("style_lock"):
        root = run_dir(state["run_id"])
        tokens = root_tokens((root / pages[key]["best"]["html_path"]).read_text())
        update["style_lock"] = {**state["style_lock"], "tokens": tokens}
        for other, saved in pages.items():
            if other != key and saved.get("best"):
                html, changed = lock_tokens((root / saved["best"]["html_path"]).read_text(), tokens)
                (root / "site" / page_spec(state, other)["file"]).write_text(html)
                if changed:
                    emit("tokens_locked", page_id=other, changed=changed)
    return update
