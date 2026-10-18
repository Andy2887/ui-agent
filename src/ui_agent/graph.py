"""Top-level StateGraph wiring (plan §3.1)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.final_approval import final_approval
from .nodes.handoff import build_handoff, export
from .nodes.intake import intake, kickoff
from .nodes.memory_nodes import load_memory, update_memory
from .nodes.pages import build_page, collect_pages, next_pages, route_pages, sketch_review
from .nodes.planner import fan_out, plan_direction
from .nodes.sketch import sketch_page
from .state import AgentState


def build_graph(checkpointer=None, store=None):
    g = StateGraph(AgentState)
    g.add_node("intake", intake)
    g.add_node("kickoff", kickoff)
    g.add_node("load_memory", load_memory)
    g.add_node("plan_direction", plan_direction)
    g.add_node("sketch_page", sketch_page)
    g.add_node("sketch_review", sketch_review)
    g.add_node("next_pages", next_pages)
    g.add_node("build_page", build_page)
    g.add_node("collect_pages", collect_pages)
    g.add_node("final_approval", final_approval)
    g.add_node("build_handoff", build_handoff)
    g.add_node("export", export)
    g.add_node("update_memory", update_memory)

    g.add_edge(START, "intake")
    g.add_edge("intake", "kickoff")
    # kickoff → intake (answers given) | load_memory (Command)
    g.add_edge("load_memory", "plan_direction")
    g.add_conditional_edges("plan_direction", fan_out, ["sketch_page"])
    g.add_edge("sketch_page", "sketch_review")
    # sketch_review → next_pages | plan_direction (Command)
    # Pages run in batches: the key page alone, then all the rest in parallel (Send ×pages). Each build_page
    # designs one page and runs its refine loop in a private state.
    g.add_conditional_edges("next_pages", route_pages, ["build_page", "final_approval"])
    g.add_edge("build_page", "collect_pages")
    g.add_edge("collect_pages", "next_pages")
    # final_approval → build_handoff | next_pages (Command)
    g.add_edge("build_handoff", "export")
    g.add_edge("export", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile(checkpointer=checkpointer, store=store)
