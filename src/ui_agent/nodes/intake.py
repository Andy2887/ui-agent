"""4.1 intake: turn the PM's brief and user flows into a design brief with a site map. 4.2 kickoff
(interrupt #1): the designer's clarifying questions, asked only when the brief leaves something important open."""

from __future__ import annotations

import json
import re
from typing import Literal

from langgraph.types import Command, interrupt

from .. import mock, settings
from ..llm import get_llm
from ..state import MAX_PAGES, AgentState, IntakeResult, PagePlan, brief_text
from .common import emit

MAX_QUESTIONS = 3


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "page"


def plan_site(result: IntakeResult) -> IntakeResult:
    """Code-side guarantees on the site map: unique ids, known page types, at most MAX_PAGES pages with the
    entry page of flow 1 first, flow steps on real pages, a link for every step that changes page, file names."""
    pages: dict[str, PagePlan] = {}
    renamed: dict[str, str] = {}
    for p in result.pages:
        pid = base = _slug(p.id or p.name)
        n = 2
        while pid in pages:
            pid, n = f"{base}-{n}", n + 1
        renamed.setdefault(p.id, pid)
        if not settings.page_type(p.page_type):
            result.assumptions.append(f"{p.name}: unknown page type {p.page_type!r}; treated as a landing page.")
            p.page_type = "landing"
        if not p.sections:
            p.sections = list(settings.page_type(p.page_type)["default_sections"])
        pages[pid] = p.model_copy(update={"id": pid})
    if not pages:
        pages["home"] = PagePlan(id="home", name="Home", page_type="landing", purpose=result.problem,
                                 primary_action="Get started", sections=list(settings.page_type("landing")["default_sections"]),
                                 links_to=[])
        result.assumptions.append("No pages came back from the flows; designed a single home page.")
    for p in pages.values():
        p.links_to = [renamed.get(l, _slug(l)) for l in p.links_to]
    for f in result.flows:
        for st in f.steps:
            st.page = renamed.get(st.page, _slug(st.page))

    # The entry page of flow 1 is the key page: it is designed first and sets the look for the rest.
    order = list(pages)
    entry = next((st.page for f in result.flows[:1] for st in f.steps if st.page in pages), order[0])
    order.remove(entry)
    order.insert(0, entry)
    keep, dropped = order[:MAX_PAGES], order[MAX_PAGES:]
    result.not_designed = [pages[pid].name for pid in dropped]

    for f in result.flows:
        f.steps = [st for st in f.steps if st.page in keep]
        for a, b in zip(f.steps, f.steps[1:]):
            if a.page != b.page and b.page not in pages[a.page].links_to:
                pages[a.page].links_to.append(b.page)
    for i, pid in enumerate(keep):
        p = pages[pid]
        p.links_to = [l for l in dict.fromkeys(p.links_to) if l in keep and l != pid]
        p.file = "index.html" if i == 0 else f"{pid}.html"
    result.pages = [pages[pid] for pid in keep]
    return result


async def intake(state: AgentState) -> dict:
    brief = state["brief"]
    answers = (state.get("kickoff") or {}).get("answers") or []
    emit("node", node="intake", status="started")
    section_ids = [s["id"] for s in settings.presets()["layouts"]["sections"]]
    page_types = [p["id"] for p in settings.presets()["layouts"]["page_types"]]
    system = (settings.prompt("intake").replace("{section_ids}", ", ".join(section_ids))
              .replace("{page_types}", ", ".join(page_types)).replace("{max_pages}", str(MAX_PAGES))
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
    result = plan_site(result)
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
