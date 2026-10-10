"""Refine loop subgraph (plan §4.8): render → audit → review → gate → execute → render …"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.executor import execute
from .nodes.gate import gate, route_after_gate
from .nodes.reviewer import audit_node, render_node, review
from .state import AgentState


def entry(state: AgentState) -> str:
    # Developer change requests (gallery notes, final-review feedback) are applied before the next review.
    return "execute" if state.get("change_requests_pending") else "render"


def build_refine_graph():
    g = StateGraph(AgentState)
    g.add_node("render", render_node)
    g.add_node("audit", audit_node)
    g.add_node("review", review)
    g.add_node("gate", gate)
    g.add_node("execute", execute)
    g.add_conditional_edges(START, entry, {"execute": "execute", "render": "render"})
    g.add_edge("render", "audit")
    g.add_edge("audit", "review")
    g.add_edge("review", "gate")
    g.add_conditional_edges("gate", route_after_gate, {"execute": "execute", "done": END})
    g.add_conditional_edges("execute", lambda s: "done" if s.get("gate_decision") == "stop" else "render",
                            {"render": "render", "done": END})
    return g.compile()


_app = None


async def refine(state: AgentState, config) -> dict:
    """Run the subgraph and return only its *changes*.

    A compiled subgraph used directly as a node writes its whole output back through the
    parent's reducers, which would double-count list/usage channels (history, usage,
    candidates). Returning a delta keeps the parent state exact."""
    global _app
    if _app is None:
        _app = build_refine_graph()
    out = await _app.ainvoke(state, config)
    hist0 = len(state.get("history") or [])
    usage0 = state.get("usage") or {}
    delta = {k: v for k, v in out.items() if k not in ("history", "usage", "candidates")}
    delta["history"] = (out.get("history") or [])[hist0:]
    delta["usage"] = {k: v - usage0.get(k, 0) for k, v in (out.get("usage") or {}).items() if v != usage0.get(k, 0)}
    return delta
