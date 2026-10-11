"""4.3 load_memory and 4.13 update_memory."""

from __future__ import annotations

from langgraph.store.base import BaseStore

from ..memory import store as memory
from ..state import AgentState, brief_text
from .common import emit


async def load_memory(state: AgentState, *, store: BaseStore) -> dict:
    ctx = await memory.load_context(store, state["user_id"])
    emit("memory", taste=ctx["taste"], lessons=[l["id"] for l in ctx["lessons"]])
    return {"memory_context": ctx}


async def update_memory(state: AgentState, *, store: BaseStore) -> dict:
    issues = list(state.get("issues") or [])
    await memory.record_lessons(store, state["run_id"], issues)
    best = state.get("best") or state.get("current") or {}
    await memory.record_run(store, state["user_id"], state["run_id"], {
        "prompt": brief_text(state["brief"])[:300],
        "chosen_direction": (state.get("selection") or {}).get("id"),
        "iterations": state.get("iteration"),
        "final_score": best.get("score"),
        "stop_reason": state.get("stop_reason"),
        "cost_usd": round((state.get("usage") or {}).get("cost_usd", 0.0), 4),
    })
    emit("done", stop_reason=state.get("stop_reason"), score=best.get("score"))
    return {}
