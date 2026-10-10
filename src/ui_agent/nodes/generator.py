"""4.4 generate_design (×N via Send). Renders and audits its own output so the
Generating screen can show each card as soon as it is ready."""

from __future__ import annotations

import asyncio
import json

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..state import DirectionBrief
from .common import emit, extract_html, pref_summary, run_dir
from .render import render_design

_sem: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(int(settings.config()["max_parallel_generations"]))
    return _sem


def generator_content(payload: dict) -> str:
    brief = payload["brief"]
    lessons = payload.get("lessons") or []
    parts = [
        f"<request>\n{payload['prompt']}\n</request>",
        f"<page>\n{json.dumps(payload['intake'], indent=1)}\n</page>",
        f"<direction_brief>\n{json.dumps(brief, indent=1)}\n</direction_brief>",
        f"<locked_preferences>\n{json.dumps(pref_summary(payload['preferences']), indent=1)}\n</locked_preferences>",
        f"<theme>{payload['preferences'].get('theme', 'light')} (for 'both': light on :root plus a prefers-color-scheme: dark override using dark_palette)</theme>",
    ]
    if lessons:
        parts.append("<preflight_checklist>\nMistakes earlier designs made repeatedly. Avoid them:\n"
                     + "\n".join(f"- {l['id']}: {l.get('pattern', '')} → {l.get('fix', '')}" for l in lessons) + "\n</preflight_checklist>")
    return "\n\n".join(parts)


async def generate_design(payload: dict) -> dict:
    brief = payload["brief"]
    run_id = payload["run_id"]
    did = brief["id"]
    emit("candidate_started", id=did, name=brief["name"])
    out = run_dir(run_id) / "candidates" / did
    out.mkdir(parents=True, exist_ok=True)
    design = {"direction_id": did, "version": 1, "html_path": f"candidates/{did}/v1.html"}
    usage: dict = {}
    try:
        async with _semaphore():
            system = settings.prompt("generator").replace("{html_contract}", settings.prompt("html_contract"))
            text, usage = await get_llm().text(
                "generator", system=system, content=generator_content(payload),
                mock=lambda: mock.html_for(DirectionBrief(**brief), payload["preferences"], payload["intake"]),
            )
            (out / "v1.html").write_text(extract_html(text))
        design, _ = await render_design(run_id, design, f"candidates/{did}/shots")
    except (LLMError, ValueError) as e:
        design["error"] = str(e)
    emit("candidate_ready", id=did, design=design, brief=brief)
    return {"candidates": [design], "usage": usage}
