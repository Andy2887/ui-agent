"""4.4 plan_directions: N distinct directions (UX concept + visual mood), with code-enforced
diversity and contrast repair. The designer owns every visual decision; presets are its library."""

from __future__ import annotations

import json

from langgraph.types import Send

from .. import mock, settings
from ..color import check_palette, repair_palette
from ..library import design_library, industry_priors
from ..llm import LLMError, get_llm, over_budget
from ..state import AgentState, DirectionBrief, Palette, PlanResult, usage_reducer as add_usage
from .common import emit

MAX_PLAN_ATTEMPTS = 3
MIN_DIFFERING_AXES = 3


def slots_for(n: int, has_taste: bool) -> list[str]:
    """Composition rule (§4.4). After the first neutral, the middle slots alternate bold and neutral, so a
    run never offers two safe answers side by side."""
    if n == 1:
        return ["taste" if has_taste else "neutral"]
    if n == 2:
        return ["taste", "neutral"] if has_taste else ["neutral", "bold"]
    taste = max(1, round(0.4 * n)) if has_taste else 0
    taste = min(taste, n - 1)
    middle = ["neutral" if i % 2 == 0 else "bold" for i in range(n - taste - 1)]
    return ["taste"] * taste + middle + ["wildcard"]


def _fonts(b: DirectionBrief) -> set[str]:
    return {b.heading_font.strip().lower(), b.body_font.strip().lower()}


def diversity_problems(briefs: list[DirectionBrief]) -> list[str]:
    problems = []
    for i, a in enumerate(briefs):
        for b in briefs[i + 1:]:
            same_layout = (a.layout_id and a.layout_id == b.layout_id) or a.layout_archetype.strip().lower() == b.layout_archetype.strip().lower()
            if same_layout and a.reference_style.lower() == b.reference_style.lower():
                problems.append(f"Briefs {a.id} and {b.id} share the same layout archetype and reference style.")
            differing = sum([
                a.layout_archetype != b.layout_archetype, (a.heading_font, a.body_font) != (b.heading_font, b.body_font),
                a.palette.primary.lower() != b.palette.primary.lower(), a.density != b.density,
                a.reference_style != b.reference_style, a.sections != b.sections, a.theme != b.theme,
                a.variance != b.variance,
            ])
            if differing < MIN_DIFFERING_AXES:
                problems.append(f"Briefs {a.id} and {b.id} differ on only {differing} axes (need {MIN_DIFFERING_AXES}).")
            if a.signature_element.strip().lower() == b.signature_element.strip().lower():
                problems.append(f"Briefs {a.id} and {b.id} have the same signature element.")
            if a.concept.strip().lower() == b.concept.strip().lower():
                problems.append(f"Briefs {a.id} and {b.id} have the same concept.")
            if shared := _fonts(a) & _fonts(b):
                problems.append(f"Briefs {a.id} and {b.id} both use {', '.join(sorted(shared))}; every direction needs its own fonts.")
            if a.style_id and a.style_id == b.style_id:
                problems.append(f"Briefs {a.id} and {b.id} use the same library style ({a.style_id}).")
            if a.structure_id and a.structure_id == b.structure_id:
                problems.append(f"Briefs {a.id} and {b.id} use the same page structure ({a.structure_id}).")
    need = min(len(briefs), 3)
    levels = sorted({b.variance for b in briefs})
    if len(levels) < need:
        problems.append(f"The directions use variance {', '.join(levels)}; {need} directions need {need} different "
                        "levels (low, mid, high).")
    return problems


def repair_contrast(brief: DirectionBrief) -> list[str]:
    if not check_palette(brief.palette.model_dump()):
        return []
    fixed, notes = repair_palette(brief.palette.model_dump())
    brief.palette = Palette(**fixed)
    return [f"{brief.id}: {n}" for n in notes]


async def plan_directions(state: AgentState) -> dict:
    n = state["candidate_count"]
    taste = (state.get("memory_context") or {}).get("taste") or {}
    slots = slots_for(n, bool(taste.get("has_signal")))
    intake = {k: v for k, v in state["intake"].items() if k != "questions"}
    emit("node", node="plan_directions", status="started", count=n)

    if over_budget(state.get("usage")):
        raise LLMError("Per-run budget exhausted before planning.")

    priors = industry_priors(state["brief"], intake)
    # A fresh sample per run and per regenerate, fixed across retries within one planning call.
    library = design_library(state["brief"], intake, priors, seed=f"{state['run_id']}:{state.get('regenerate_feedback') or ''}")
    emit("library", industries=[p["name"] for p in priors], styles=[s["id"] for s in library["reference_styles"]],
         structures=[s["id"] for s in library["page_structures"]])

    usage_total: dict = {}
    feedback: list[str] = []
    result: PlanResult | None = None
    for attempt in range(MAX_PLAN_ATTEMPTS):
        content = json.dumps({
            "pm_brief": state["brief"],
            "design_brief": intake,
            "kickoff_answers": (state.get("kickoff") or {}).get("answers") or None,
            "n": n,
            "slots": [{"id": chr(ord('a') + i), "slot": slots[i]} for i in range(n)],
            "industry_priors": priors or None,
            "library": library,
            "remembered_taste": taste if taste.get("has_signal") else None,
            "regenerate_feedback": state.get("regenerate_feedback"),
            "previous_directions_to_move_away_from": [
                {"name": b["name"], "concept": b["concept"], "layout_archetype": b["layout_archetype"],
                 "reference_style": b["reference_style"]}
                for b in (state.get("briefs") or [])] if state.get("regenerate_feedback") else None,
            "problems_with_previous_attempt": feedback or None,
        }, indent=1)
        result, usage = await get_llm().parse(
            "planner", system=settings.prompt("planner"), content=content, output_format=PlanResult,
            mock=lambda a=attempt: mock.plan(n, intake, slots, a),
        )
        usage_total = add_usage(usage_total, usage)
        briefs = result.briefs[:n]
        if len(briefs) < n:
            feedback = [f"Returned {len(briefs)} briefs; exactly {n} are required."]
            continue
        for i, b in enumerate(briefs):
            b.id = chr(ord("a") + i)
            b.slot = slots[i]  # type: ignore[assignment]
            if not b.sections:
                b.sections = list(intake["sections"])
        feedback = diversity_problems(briefs)
        if not feedback:
            break
        emit("plan_retry", attempt=attempt + 1, problems=feedback)
    assert result is not None
    briefs = result.briefs[:n]
    repair_notes = [note for b in briefs for note in repair_contrast(b)]

    brief_dicts = [b.model_dump() for b in briefs]
    emit("briefs", briefs=brief_dicts, repairs=repair_notes, unresolved=feedback)
    return {
        "briefs": brief_dicts,
        "candidates": [{"__reset__": True}],
        "selection": None,
        "usage": usage_total,
    }


def fan_out(state: AgentState) -> list[Send]:
    return [
        Send("sketch_direction", {
            "run_id": state["run_id"], "brief": state["brief"], "intake": state["intake"],
            "kickoff": state.get("kickoff"), "direction": d,
        })
        for d in state["briefs"]
    ]
