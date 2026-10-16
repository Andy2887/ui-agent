"""4.4 plan_direction: one direction (UX concept + design system) for the whole site, with contrast repair.
The designer owns every visual decision; presets are its library. Then one sketch per page (fan_out)."""

from __future__ import annotations

import json

from langgraph.types import Send

from .. import mock, settings
from ..color import check_palette, repair_palette
from ..library import design_library, industry_priors
from ..llm import LLMError, get_llm, over_budget
from ..state import AgentState, DirectionBrief, Palette
from .common import emit


def repair_contrast(brief: DirectionBrief) -> list[str]:
    if not check_palette(brief.palette.model_dump()):
        return []
    fixed, notes = repair_palette(brief.palette.model_dump())
    brief.palette = Palette(**fixed)
    return notes


async def plan_direction(state: AgentState) -> dict:
    taste = (state.get("memory_context") or {}).get("taste") or {}
    slot = "taste" if taste.get("has_signal") else "neutral"
    intake = {k: v for k, v in state["intake"].items() if k != "questions"}
    feedback = state.get("revise_feedback")
    emit("node", node="plan_direction", status="started")

    if over_budget(state.get("usage")):
        raise LLMError("Per-run budget exhausted before planning.")

    priors = industry_priors(state["brief"], intake)
    # A fresh sample per run and per revision.
    library = design_library(state["brief"], intake, priors, seed=f"{state['run_id']}:{feedback or ''}")
    emit("library", industries=[p["name"] for p in priors], styles=[s["id"] for s in library["reference_styles"]],
         structures=[s["id"] for s in library["page_structures"]])

    previous = state.get("direction") if feedback else None
    content = json.dumps({
        "pm_brief": state["brief"],
        "design_brief": intake,
        "kickoff_answers": (state.get("kickoff") or {}).get("answers") or None,
        "slot": slot,
        "industry_priors": priors or None,
        "library": library,
        "remembered_taste": taste if taste.get("has_signal") else None,
        "pm_feedback": feedback,
        "previous_direction": previous,
    }, indent=1)
    direction, usage = await get_llm().parse(
        "planner", system=settings.prompt("planner"), content=content, output_format=DirectionBrief,
        mock=lambda: mock.plan(intake, slot, revision=len(state.get("rejected_directions") or [])),
    )
    direction.id, direction.slot = "a", slot  # type: ignore[assignment]
    repairs = repair_contrast(direction)

    d = direction.model_dump()
    emit("direction", direction=d, repairs=repairs)
    return {"direction": d, "sketches": [{"__reset__": True}], "usage": usage}


def fan_out(state: AgentState) -> list[Send]:
    return [
        Send("sketch_page", {
            "run_id": state["run_id"], "brief": state["brief"], "intake": state["intake"],
            "kickoff": state.get("kickoff"), "direction": state["direction"], "page": page,
            "feedback": state.get("revise_feedback"),
        })
        for page in state["intake"]["pages"]
    ]
