"""4.1 intake: turn the PM's brief into a design brief. 4.2 kickoff (interrupt #1): the
designer's clarifying questions, asked only when the brief leaves something important open."""

from __future__ import annotations

import json
from typing import Literal

from langgraph.types import Command, interrupt

from .. import mock, settings
from ..llm import get_llm
from ..state import AgentState, IntakeResult, brief_text
from .common import emit

MAX_QUESTIONS = 3


async def intake(state: AgentState) -> dict:
    brief = state["brief"]
    answers = (state.get("kickoff") or {}).get("answers") or []
    emit("node", node="intake", status="started")
    section_ids = [s["id"] for s in settings.presets()["layouts"]["sections"]]
    system = (settings.prompt("intake").replace("{section_ids}", ", ".join(section_ids))
              .replace("{max_questions}", str(MAX_QUESTIONS)))
    content = f"<pm_brief>\n{brief_text(brief)}\n</pm_brief>"
    if answers:
        content += ("\n\n<kickoff_answers>\nYou already asked your questions; these are the PM's answers. "
                    "Do not ask more.\n" + json.dumps(answers, indent=1) + "\n</kickoff_answers>")
    result, usage = await get_llm().parse(
        "intake", system=system, content=content, output_format=IntakeResult,
        mock=lambda: mock.intake(brief, answers),
    )
    if brief.get("product_name"):
        result.product_name = brief["product_name"]
    if not settings.page_type(result.page_type):
        result.assumptions.append(f"Unknown page type {result.page_type!r}; treated as a landing page.")
        result.page_type = "landing"
    if not result.sections:
        result.sections = settings.page_type(result.page_type)["default_sections"]
    result.questions = [] if answers else result.questions[:MAX_QUESTIONS]

    emit("intake", intake=result.model_dump())
    return {"intake": result.model_dump(), "usage": usage}


async def kickoff(state: AgentState) -> Command[Literal["intake", "load_memory"]]:
    questions = state["intake"].get("questions") or []
    if not questions or state.get("kickoff"):
        return Command(goto="load_memory")
    answer = interrupt({"kind": "kickoff", "intake": state["intake"], "questions": questions})

    given = answer.get("answers") or {}
    answers = [{"id": q["id"], "question": q["question"], "answer": given[q["id"]].strip()}
               for q in questions if (given.get(q["id"]) or "").strip()]
    if not answers:
        emit("kickoff_skipped")
        return Command(goto="load_memory", update={"kickoff": {"answers": [], "skipped": True}})
    emit("kickoff_answered", answers=answers)
    # Re-read the brief with the answers so the assumptions and sections reflect them.
    return Command(goto="intake", update={"kickoff": {"answers": answers, "skipped": False}})
