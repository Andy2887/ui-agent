"""4.5 sketch_direction (×N via Send): one low-fidelity wireframe per direction. Each renders
its own screenshots so the Sketching screen can show every card as soon as it is ready."""

from __future__ import annotations

import asyncio
import json
import re
import weakref

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..state import DirectionBrief, brief_text
from .common import emit, extract_html, run_dir
from .render import render_sketch

_sems: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


def _semaphore() -> asyncio.Semaphore:
    """One parallelism cap per event loop (a semaphore can't be shared across loops)."""
    loop = asyncio.get_running_loop()
    if loop not in _sems:
        _sems[loop] = asyncio.Semaphore(int(settings.config()["max_parallel_generations"]))
    return _sems[loop]


def sketch_kit() -> str:
    return (settings.ROOT / "prompts" / "sketch_kit.css").read_text()


def with_kit(html: str) -> str:
    """Put the shared sketch stylesheet first in <head>, so every sketch looks hand-made the same way."""
    kit = f"<style data-sketch-kit>\n{sketch_kit()}</style>"
    html = re.sub(r"<style data-sketch-kit>.*?</style>\s*", "", html, flags=re.S)
    html, n = re.subn(r"(<head[^>]*>)", lambda m: f"{m.group(1)}\n{kit}", html, count=1, flags=re.I)
    if not n:
        html = re.sub(r"(<html[^>]*>)", lambda m: f"{m.group(1)}\n<head>{kit}</head>", html, count=1, flags=re.I)
    return html


def sketcher_content(payload: dict) -> str:
    answers = (payload.get("kickoff") or {}).get("answers") or []
    design_brief = {k: v for k, v in payload["intake"].items() if k != "questions"}
    parts = [
        f"<pm_brief>\n{brief_text(payload['brief'])}\n</pm_brief>",
        f"<design_brief>\n{json.dumps(design_brief, indent=1)}\n</design_brief>",
    ]
    if answers:
        parts.append(f"<kickoff_answers>\n{json.dumps(answers, indent=1)}\n</kickoff_answers>")
    parts.append(f"<direction>\n{json.dumps(payload['direction'], indent=1)}\n</direction>")
    return "\n\n".join(parts)


async def sketch_direction(payload: dict) -> dict:
    direction = payload["direction"]
    run_id = payload["run_id"]
    did = direction["id"]
    emit("candidate_started", id=did, name=direction["name"])
    out = run_dir(run_id) / "sketches" / did
    out.mkdir(parents=True, exist_ok=True)
    sketch = {"direction_id": did, "version": 0, "html_path": f"sketches/{did}/sketch.html"}
    usage: dict = {}
    try:
        async with _semaphore():
            system = settings.prompt("sketcher").replace("{sketch_contract}", settings.prompt("sketch_contract")) \
                .replace("{sketch_kit}", sketch_kit())
            text, usage = await get_llm().text(
                "sketcher", system=system, content=sketcher_content(payload),
                mock=lambda: mock.sketch_for(DirectionBrief(**direction), payload["intake"]),
            )
            (out / "sketch.html").write_text(with_kit(extract_html(text)))
        sketch = await render_sketch(run_id, sketch, f"sketches/{did}/shots")
    except (LLMError, ValueError) as e:
        sketch["error"] = str(e)
    emit("candidate_ready", id=did, design=sketch, brief=direction)
    return {"candidates": [sketch], "usage": usage}
