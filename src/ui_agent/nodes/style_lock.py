"""4.7 lock_style: StyleSpec from the chosen design (deterministic tokens + LLM character + locked prefs)."""

from __future__ import annotations

import json
import shutil

from .. import mock, settings
from ..state import AgentState, StyleCharacter, StyleSpec
from ..llm import get_llm
from .common import emit, image_block, pref_summary, root_tokens, run_dir


async def lock_style(state: AgentState) -> dict:
    pick = state["selection"]["id"]
    notes = state["selection"].get("notes") or ""
    design = next(d for d in state["candidates"] if d["direction_id"] == pick)
    brief = next(b for b in state["briefs"] if b["id"] == pick)
    root = run_dir(state["run_id"])
    html = (root / design["html_path"]).read_text()
    tokens = root_tokens(html)

    content: list = []
    tiles = (design.get("tiles") or {}).get("desktop") or []
    if tiles:
        content.append(image_block(root / tiles[0]))
    content.append({"type": "text", "text": "\n\n".join([
        f"<direction_brief>\n{json.dumps(brief, indent=1)}\n</direction_brief>",
        f"<design_tokens>\n{json.dumps(tokens, indent=1)}\n</design_tokens>",
        f"<user_notes>{notes or '(none)'}</user_notes>",
    ])})
    character, usage = await get_llm().parse(
        "style_lock", system=settings.prompt("style_lock"), content=content, output_format=StyleCharacter,
        mock=lambda: mock.style_character(brief, notes),
    )
    spec = StyleSpec(direction_id=pick, tokens=tokens, character=character.character,
                     signature_elements=character.signature_elements, must_keep=character.must_keep,
                     user_notes=notes, locked_preferences=pref_summary(state["preferences"]))

    # Refinement works on its own copy: refine/v1.html is the chosen candidate.
    (root / "refine").mkdir(exist_ok=True)
    shutil.copyfile(root / design["html_path"], root / "refine" / "v1.html")
    current = {"direction_id": pick, "version": 1, "html_path": "refine/v1.html"}

    change_requests = []
    if notes:
        change_requests.append({
            "id": "chg_gallery_notes", "criterion": "B9", "severity": "high", "selector": "body", "viewport": "all",
            "evidence": f"Developer's note when picking this direction: {notes}",
            "suggested_fix": notes, "status": "open",
            "explanation": "You asked for this when you picked the design, so it's applied before anything else.",
        })
    emit("style_locked", spec=spec.model_dump())
    return {
        "style_lock": spec.model_dump(), "current": current, "best": None, "iteration": 0,
        "iteration_cap": int(settings.config()["refine"]["max_iterations"]),
        "issues": change_requests, "change_requests": change_requests, "resolved_issue_ids": [],
        "stop_reason": None, "regression_note": None, "usage": usage,
        "change_requests_pending": bool(change_requests),
    }
