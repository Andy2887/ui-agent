"""Top-level StateGraph wiring (plan §3.1)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.final_approval import final_approval
from .nodes.gallery import gallery, render_and_audit_all
from .nodes.generator import generate_design
from .nodes.handoff import build_handoff, export
from .nodes.intake import intake
from .nodes.memory_nodes import load_memory, update_memory
from .nodes.planner import fan_out, plan_directions
from .nodes.style_lock import lock_style
from .refine_graph import refine
from .state import AgentState


def build_graph(checkpointer=None, store=None):
    g = StateGraph(AgentState)
    g.add_node("intake", intake)
    g.add_node("load_memory", load_memory)
    g.add_node("plan_directions", plan_directions)
    g.add_node("generate_design", generate_design)
    g.add_node("render_and_audit_all", render_and_audit_all)
    g.add_node("gallery", gallery)
    g.add_node("lock_style", lock_style)
    g.add_node("refine", refine)
    g.add_node("final_approval", final_approval)
    g.add_node("build_handoff", build_handoff)
    g.add_node("export", export)
    g.add_node("update_memory", update_memory)

    g.add_edge(START, "intake")
    g.add_edge("intake", "load_memory")
    g.add_edge("load_memory", "plan_directions")
    g.add_conditional_edges("plan_directions", fan_out, ["generate_design"])
    g.add_edge("generate_design", "render_and_audit_all")
    g.add_edge("render_and_audit_all", "gallery")
    # gallery → lock_style | plan_directions (Command)
    g.add_edge("lock_style", "refine")
    g.add_edge("refine", "final_approval")
    # final_approval → build_handoff | refine (Command)
    g.add_edge("build_handoff", "export")
    g.add_edge("export", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile(checkpointer=checkpointer, store=store)
