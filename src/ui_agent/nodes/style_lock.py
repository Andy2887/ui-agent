"""4.8 lock_style: StyleSpec from the first full design (deterministic tokens + LLM character)."""

from __future__ import annotations

import json

from .. import mock, settings
from ..state import AgentState, StyleCharacter, StyleSpec
from ..llm import get_llm
from .common import emit, image_block, root_tokens, run_dir


async def lock_style(state: AgentState) -> dict:
    pick = state["selection"]["id"]
    notes = state["selection"].get("notes") or ""
    first = state["design"]
    brief = next(b for b in state["briefs"] if b["id"] == pick)
    root = run_dir(state["run_id"])
    html = (root / first["html_path"]).read_text()
    tokens = root_tokens(html)

    content: list = []
    tiles = (first.get("tiles") or {}).get("desktop") or []
    if tiles:
        content.append(image_block(root / tiles[0]))
    content.append({"type": "text", "text": "\n\n".join([
        f"<direction_brief>\n{json.dumps(brief, indent=1)}\n</direction_brief>",
        f"<design_tokens>\n{json.dumps(tokens, indent=1)}\n</design_tokens>",
        f"<pm_notes>{notes or '(none)'}</pm_notes>",
    ])})
    character, usage = await get_llm().parse(
        "style_lock", system=settings.prompt("style_lock"), content=content, output_format=StyleCharacter,
        mock=lambda: mock.style_character(brief, notes),
    )
    spec = StyleSpec(direction_id=pick, tokens=tokens, character=character.character,
                     signature_elements=character.signature_elements, must_keep=character.must_keep,
                     user_notes=notes)

    current = {"direction_id": pick, "version": 1, "html_path": first["html_path"]}
    # The designer already applied the PM's notes; the reviewer verifies them like any other issue.
    issues = []
    if notes:
        issues.append({
            "id": "chg_gallery_notes", "criterion": "B9", "severity": "high", "selector": "body", "viewport": "all",
            "evidence": f"PM's note when picking this sketch: {notes}",
            "suggested_fix": notes, "status": "open",
            "explanation": "You asked for this when you picked the sketch, so the reviewer checks it was applied.",
        })
    emit("style_locked", spec=spec.model_dump())
    return {
        "style_lock": spec.model_dump(), "current": current, "best": None, "iteration": 0,
        "iteration_cap": int(settings.config()["refine"]["max_iterations"]),
        "issues": issues, "change_requests": issues, "resolved_issue_ids": [],
        "stop_reason": None, "regression_note": None, "usage": usage,
        "change_requests_pending": False,
    }
