"""4.5 sketch_page (×pages via Send): one low-fidelity text wireframe per page of the site, all in the same
direction. Plain text keeps the sketcher's output and the designer's input small; the PM reads it as-is."""

from __future__ import annotations

import asyncio
import json
import re
import weakref

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..state import DirectionBrief, brief_text
from .common import emit, run_dir

_sems: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


def _semaphore() -> asyncio.Semaphore:
    """One parallelism cap per event loop (a semaphore can't be shared across loops)."""
    loop = asyncio.get_running_loop()
    if loop not in _sems:
        _sems[loop] = asyncio.Semaphore(int(settings.config()["max_parallel_generations"]))
    return _sems[loop]


def extract_sketch(text: str) -> str:
    """The wireframe from `DESKTOP 1440px` on, without any markdown fence around it."""
    m = re.search(r"^DESKTOP\b.*", text, flags=re.S | re.M)
    if not m:
        raise ValueError("model output did not contain a sketch starting with 'DESKTOP 1440px'")
    return re.sub(r"\n```\s*$", "", m.group(0).rstrip()) + "\n"


def sketch_notation() -> str:
    """The notation table from the sketch contract, so the designer reads sketches the way they were drawn."""
    contract = settings.prompt("sketch_contract")
    return contract[contract.index("## Notation"):contract.index("## Rules")].strip()


def site_map(intake: dict) -> list[dict]:
    """Every page in one line each, so a page links to its siblings by the right name."""
    return [{"id": p["id"], "name": p["name"], "file": p["file"], "purpose": p["purpose"], "links_to": p["links_to"]}
            for p in intake["pages"]]


def page_flows(intake: dict, page_id: str) -> list[dict]:
    """The flow steps that happen on this page, with where the user comes from and goes next."""
    out = []
    for f in intake.get("flows") or []:
        steps = f["steps"]
        for i, st in enumerate(steps):
            if st["page"] == page_id:
                out.append({"flow": f["name"], "step": i + 1, "of": len(steps), "action": st["action"],
                            "from": steps[i - 1]["page"] if i else None,
                            "next": steps[i + 1]["page"] if i + 1 < len(steps) else None})
    return out


def sketcher_content(payload: dict) -> str:
    answers = (payload.get("kickoff") or {}).get("answers") or []
    design_brief = {k: v for k, v in payload["intake"].items() if k not in ("questions", "pages")}
    page = payload["page"]
    parts = [
        f"<pm_brief>\n{brief_text(payload['brief'])}\n</pm_brief>",
        f"<design_brief>\n{json.dumps(design_brief, indent=1)}\n</design_brief>",
    ]
    if answers:
        parts.append(f"<kickoff_answers>\n{json.dumps(answers, indent=1)}\n</kickoff_answers>")
    parts += [
        f"<direction>\n{json.dumps(payload['direction'], indent=1)}\n</direction>",
        f"<site_map>\n{json.dumps(site_map(payload['intake']), indent=1)}\n</site_map>",
        f"<this_page>\n{json.dumps(page, indent=1)}\n</this_page>",
        f"<flow_steps_on_this_page>\n{json.dumps(page_flows(payload['intake'], page['id']), indent=1)}\n</flow_steps_on_this_page>",
    ]
    if payload.get("feedback"):
        parts.append(f"<pm_feedback>\nThe PM reviewed earlier sketches and asked for this:\n{payload['feedback']}\n</pm_feedback>")
    return "\n\n".join(parts)


async def sketch_page(payload: dict) -> dict:
    direction, page = payload["direction"], payload["page"]
    run_id, pid = payload["run_id"], payload["page"]["id"]
    emit("sketch_started", page_id=pid, name=page["name"])
    out = run_dir(run_id) / "sketches"
    out.mkdir(parents=True, exist_ok=True)
    sketch = {"page_id": pid, "direction_id": direction["id"], "sketch_path": f"sketches/{pid}.txt"}
    usage: dict = {}
    try:
        async with _semaphore():
            system = settings.prompt("sketcher").replace("{sketch_contract}", settings.prompt("sketch_contract"))
            text, usage = await get_llm().text(
                "sketcher", system=system, content=sketcher_content(payload),
                mock=lambda: mock.sketch_for(DirectionBrief(**direction), payload["intake"], page),
            )
        sketch["text"] = extract_sketch(text)
        (out / f"{pid}.txt").write_text(sketch["text"])
    except (LLMError, ValueError) as e:
        sketch["error"] = str(e)
    emit("sketch_ready", page_id=pid, sketch=sketch)
    return {"sketches": [sketch], "usage": usage}
