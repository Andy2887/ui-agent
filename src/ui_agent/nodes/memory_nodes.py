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


def site_score(state: dict) -> float | None:
    """The mean of the designed pages' best scores."""
    scores = [s["best"].get("score") for s in (state.get("pages") or {}).values() if s.get("best")]
    scores = [x for x in scores if x is not None]
    return round(sum(scores) / len(scores), 2) if scores else None


async def update_memory(state: AgentState, *, store: BaseStore) -> dict:
    pages = (state.get("pages") or {}).values()
    for page in pages:
        await memory.record_lessons(store, state["run_id"], list(page.get("issues") or []))
    score = site_score(state)
    stops = {pid: s.get("stop_reason") or s.get("skipped") for pid, s in (state.get("pages") or {}).items()}
    await memory.record_run(store, state["user_id"], state["run_id"], {
        "prompt": brief_text(state["brief"])[:300],
        "direction": (state.get("direction") or {}).get("name"),
        "revisions": len(state.get("rejected_directions") or []),
        "pages": len(stops),
        "final_score": score,
        "stop_reasons": stops,
        "cost_usd": round((state.get("usage") or {}).get("cost_usd", 0.0), 4),
    })
    emit("done", score=score, pages=stops)
    return {}
