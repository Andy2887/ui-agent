"""4.1 intake: page type, audience, sections. Explicit preferences always win."""

from __future__ import annotations

import json

from langgraph.store.base import BaseStore

from .. import mock, settings
from ..llm import get_llm
from ..memory import store as memory
from ..state import AgentState, IntakeResult
from .common import emit


async def intake(state: AgentState, *, store: BaseStore) -> dict:
    prefs = state["preferences"]
    emit("node", node="intake", status="started")
    section_ids = [s["id"] for s in settings.presets()["layouts"]["sections"]]
    system = settings.prompt("intake").replace("{section_ids}", ", ".join(section_ids))
    content = (
        f"<request>\n{state['prompt']}\n</request>\n\n"
        f"<explicit_preferences>\n{json.dumps({k: v for k, v in prefs.items() if v not in (None, [], '')}, indent=1)}\n</explicit_preferences>"
    )
    result, usage = await get_llm().parse(
        "intake", system=system, content=content, output_format=IntakeResult,
        mock=lambda: mock.intake(state["prompt"], prefs),
    )
    # Explicit preferences override inference.
    if prefs.get("page_type"):
        result.page_type = prefs["page_type"]
    if prefs.get("product_name"):
        result.product_name = prefs["product_name"]
    if prefs.get("sections"):
        result.sections = prefs["sections"]
    if not settings.page_type(result.page_type):
        result.assumptions.append(f"Unknown page type {result.page_type!r}; treated as a landing page.")
        result.page_type = "landing"
    if not result.sections:
        result.sections = settings.page_type(result.page_type)["default_sections"]

    await memory.record_setup(store, state["user_id"], prefs, state["candidate_count"])
    emit("intake", intake=result.model_dump())
    return {"intake": result.model_dump(), "usage": usage}
