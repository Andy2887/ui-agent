"""4.7 design: turn the chosen sketch into the first full design (refine v1). The designer makes
every visual decision here, within the direction's mood; the PM's notes are applied up front."""

from __future__ import annotations

import json

from .. import mock, settings
from ..llm import get_llm
from ..state import AgentState, DirectionBrief, brief_text
from .common import chosen_direction, emit, extract_html, image_block, run_dir
from .render import render_design


def designer_content(state: AgentState, direction: dict, sketch: dict, notes: str) -> list:
    root = run_dir(state["run_id"])
    lessons = (state.get("memory_context") or {}).get("lessons") or []
    answers = (state.get("kickoff") or {}).get("answers") or []
    design_brief = {k: v for k, v in state["intake"].items() if k != "questions"}
    content: list = []
    tiles = (sketch.get("tiles") or {}).get("desktop") or []
    if tiles:
        content.append({"type": "text", "text": "The approved sketch, first screen at 1440px:"})
        content.append(image_block(root / tiles[0]))
    parts = [
        f"<pm_brief>\n{brief_text(state['brief'])}\n</pm_brief>",
        f"<design_brief>\n{json.dumps(design_brief, indent=1)}\n</design_brief>",
    ]
    if answers:
        parts.append(f"<kickoff_answers>\n{json.dumps(answers, indent=1)}\n</kickoff_answers>")
    parts += [
        f"<direction>\n{json.dumps(direction, indent=1)}\n</direction>",
        f"<approved_sketch>\n{(root / sketch['html_path']).read_text()}\n</approved_sketch>",
        f"<pm_notes>{notes or '(none)'}</pm_notes>",
    ]
    if lessons:
        parts.append("<preflight_checklist>\nMistakes earlier designs made repeatedly. Avoid them:\n"
                     + "\n".join(f"- {l['id']}: {l.get('pattern', '')} → {l.get('fix', '')}" for l in lessons)
                     + "\n</preflight_checklist>")
    content.append({"type": "text", "text": "\n\n".join(parts)})
    return content


async def design(state: AgentState) -> dict:
    pick = state["selection"]["id"]
    notes = state["selection"].get("notes") or ""
    direction = chosen_direction(state)
    sketch = next(c for c in state["candidates"] if c["direction_id"] == pick)
    root = run_dir(state["run_id"])
    emit("design_started", id=pick, name=direction["name"])

    system = settings.prompt("generator").replace("{html_contract}", settings.prompt("html_contract"))
    text, usage = await get_llm().text(
        "generator", system=system, content=designer_content(state, direction, sketch, notes),
        mock=lambda: mock.html_for(DirectionBrief(**direction), state["intake"], notes=notes),
    )
    (root / "refine").mkdir(exist_ok=True)
    (root / "refine" / "v1.html").write_text(extract_html(text))
    first, _ = await render_design(state["run_id"], {"direction_id": pick, "version": 1, "html_path": "refine/v1.html"},
                                   "refine/v1-shots")
    emit("design_ready", id=pick, design=first)
    return {"design": first, "usage": usage}
