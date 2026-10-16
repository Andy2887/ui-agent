"""Top-level StateGraph wiring (plan §3.1)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.final_approval import final_approval
from .nodes.generator import design_page
from .nodes.handoff import build_handoff, export
from .nodes.intake import intake, kickoff
from .nodes.memory_nodes import load_memory, update_memory
from .nodes.pages import finish_page, next_page, sketch_review
from .nodes.planner import fan_out, plan_direction
from .nodes.sketch import sketch_page
from .nodes.style_lock import lock_style
from .refine_graph import refine
from .state import AgentState


def build_graph(checkpointer=None, store=None):
    g = StateGraph(AgentState)
    g.add_node("intake", intake)
    g.add_node("kickoff", kickoff)
    g.add_node("load_memory", load_memory)
    g.add_node("plan_direction", plan_direction)
    g.add_node("sketch_page", sketch_page)
    g.add_node("sketch_review", sketch_review)
    g.add_node("next_page", next_page)
    g.add_node("design_page", design_page)
    g.add_node("lock_style", lock_style)
    g.add_node("refine", refine)
    g.add_node("finish_page", finish_page)
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
    # sketch_review → next_page | plan_direction (Command)
    # next_page → design_page (new page) | refine (change requests) | final_approval (no pages left) (Command)
    # design_page → lock_style | next_page (over budget) (Command)
    g.add_edge("lock_style", "refine")
    g.add_edge("refine", "finish_page")
    g.add_edge("finish_page", "next_page")
    # final_approval → build_handoff | next_page (Command)
    g.add_edge("build_handoff", "export")
    g.add_edge("export", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile(checkpointer=checkpointer, store=store)
