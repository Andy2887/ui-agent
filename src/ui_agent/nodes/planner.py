"""4.3 plan_directions: N diverse direction briefs, with code-enforced diversity and palette checks."""

from __future__ import annotations

import json

from langgraph.types import Send

from .. import mock, settings
from ..color import check_palette, palette_from_brand, palette_matches_direction, repair_palette
from ..llm import LLMError, get_llm, over_budget
from ..state import AgentState, DirectionBrief, Palette, PlanResult, usage_reducer as add_usage
from .common import emit, open_axes, pref_summary

MAX_PLAN_ATTEMPTS = 3


def slots_for(n: int, has_taste: bool) -> list[str]:
    """Composition rule (§4.3)."""
    if n == 1:
        return ["taste" if has_taste else "neutral"]
    if n == 2:
        return ["taste" if has_taste else "neutral", "neutral"]
    taste = max(1, round(0.4 * n)) if has_taste else 0
    taste = min(taste, n - 1)
    neutral = n - taste - 1
    return ["taste"] * taste + ["neutral"] * neutral + ["wildcard"]


def layouts_for(n: int, picked: list[str]) -> list[str | None]:
    """Spread picked layouts across candidates; extras reuse picked layouts (§5.2)."""
    if not picked:
        return [None] * n
    return [picked[i % len(picked)] for i in range(n)]


def enforce_fixed(brief: DirectionBrief, prefs: dict, layout_id: str | None) -> DirectionBrief:
    """Copy every explicit choice into the brief unchanged."""
    if prefs.get("density"):
        brief.density = prefs["density"]
    if prefs.get("shape"):
        brief.shape = prefs["shape"]
    if prefs.get("motion"):
        brief.motion = prefs["motion"]
    if prefs.get("imagery"):
        brief.imagery = prefs["imagery"]
    if prefs.get("typography"):
        t = settings.typography(prefs["typography"])
        brief.heading_font, brief.body_font = t["heading"]["family"], t["body"]["family"]
    if layout_id:
        brief.layout_id = layout_id
        lay = settings.layout(layout_id)
        if lay and lay["brief"].split(":")[0].lower() not in brief.layout_archetype.lower():
            brief.layout_archetype = f"{lay['brief']} — {brief.layout_archetype}"
    if prefs.get("styles") and brief.reference_style not in prefs["styles"]:
        brief.reference_style = " + ".join(prefs["styles"])
    color = prefs.get("color")
    if color and color.get("kind") == "brand":
        # The brand color replaces the direction: the palette is built around it.
        brief.palette = Palette(**palette_from_brand(color["value"], "light"))
        brief.dark_palette = Palette(**palette_from_brand(color["value"], "dark"))
    return brief


def diversity_problems(briefs: list[DirectionBrief], prefs: dict) -> list[str]:
    problems = []
    style_fixed, layout_fixed = bool(prefs.get("styles")), bool(prefs.get("layouts"))
    for i, a in enumerate(briefs):
        for b in briefs[i + 1:]:
            if not (style_fixed and layout_fixed):
                same_layout = (a.layout_id and a.layout_id == b.layout_id) or a.layout_archetype.strip().lower() == b.layout_archetype.strip().lower()
                if same_layout and a.reference_style.lower() == b.reference_style.lower():
                    problems.append(f"Briefs {a.id} and {b.id} share the same layout archetype and reference style.")
            differing = sum([
                a.layout_archetype != b.layout_archetype, (a.heading_font, a.body_font) != (b.heading_font, b.body_font),
                a.palette.primary.lower() != b.palette.primary.lower(), a.density != b.density,
                a.reference_style != b.reference_style,
            ])
            needed = min(3, len(open_axes(prefs)))
            if differing < needed:
                problems.append(f"Briefs {a.id} and {b.id} differ on only {differing} axes (need {needed}).")
            if a.signature_element.strip().lower() == b.signature_element.strip().lower():
                problems.append(f"Briefs {a.id} and {b.id} have the same signature element.")
    return problems


def palette_problems(brief: DirectionBrief, prefs: dict) -> list[str]:
    color = prefs.get("color")
    if not color or color.get("kind") != "direction":
        return []
    d = settings.color_direction(color["value"])
    return [f"Brief {brief.id}: {p}" for p in palette_matches_direction(brief.palette.model_dump(), d)] if d else []


def repair_contrast(brief: DirectionBrief) -> list[str]:
    notes = []
    for attr in ("palette", "dark_palette"):
        pal = getattr(brief, attr)
        if pal is None:
            continue
        if check_palette(pal.model_dump()):
            fixed, n = repair_palette(pal.model_dump())
            setattr(brief, attr, Palette(**fixed))
            notes += [f"{brief.id} ({'dark' if attr == 'dark_palette' else 'light'}): {x}" for x in n]
    return notes


async def plan_directions(state: AgentState) -> dict:
    n = state["candidate_count"]
    prefs = state["preferences"]
    taste = (state.get("memory_context") or {}).get("taste") or {}
    slots = slots_for(n, bool(taste.get("has_signal")))
    layouts = layouts_for(n, prefs.get("layouts") or [])
    page_type = state["intake"]["page_type"]
    page_layouts = [{"id": l["id"], "name": l["name"], "brief": l["brief"]}
                    for l in settings.presets()["layouts"]["layouts"] if l["page_type"] == page_type]
    emit("node", node="plan_directions", status="started", count=n)

    if over_budget(state.get("usage")):
        raise LLMError("Per-run budget exhausted before planning.")

    usage_total: dict = {}
    feedback: list[str] = []
    result: PlanResult | None = None
    for attempt in range(MAX_PLAN_ATTEMPTS):
        content = json.dumps({
            "request": state["prompt"],
            "intake": state["intake"],
            "n": n,
            "fixed_choices": pref_summary(prefs),
            "open_axes": open_axes(prefs),
            "slots": [{"id": chr(ord('a') + i), "slot": slots[i], "assigned_layout_id": layouts[i]} for i in range(n)],
            "available_layouts_for_page_type": page_layouts,
            "remembered_taste": taste if taste.get("has_signal") else None,
            "regenerate_feedback": state.get("regenerate_feedback"),
            "previous_directions_to_move_away_from": [
                {"name": b["name"], "layout_archetype": b["layout_archetype"], "reference_style": b["reference_style"]}
                for b in (state.get("briefs") or [])] if state.get("regenerate_feedback") else None,
            "problems_with_previous_attempt": feedback or None,
        }, indent=1)
        result, usage = await get_llm().parse(
            "planner", system=settings.prompt("planner"), content=content, output_format=PlanResult,
            mock=lambda a=attempt: mock.plan(n, prefs, slots, layouts, a),
        )
        usage_total = add_usage(usage_total, usage)
        briefs = result.briefs[:n]
        if len(briefs) < n:
            feedback = [f"Returned {len(briefs)} briefs; exactly {n} are required."]
            continue
        for i, b in enumerate(briefs):
            b.id = chr(ord("a") + i)
            b.slot = slots[i]  # type: ignore[assignment]
            enforce_fixed(b, prefs, layouts[i])
        feedback = diversity_problems(briefs, prefs) + [p for b in briefs for p in palette_problems(b, prefs)]
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
        Send("generate_design", {
            "run_id": state["run_id"], "prompt": state["prompt"], "preferences": state["preferences"],
            "intake": state["intake"], "brief": b,
            "lessons": (state.get("memory_context") or {}).get("lessons", []),
        })
        for b in state["briefs"]
    ]

