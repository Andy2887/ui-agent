"""4.10 build_handoff, 4.11 export."""

from __future__ import annotations

import json
import re
import shutil
import zipfile

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..state import AgentState
from ..tools.browser import get_browser
from .common import dump_json, emit, root_tokens, run_dir


def w3c_tokens(tokens: dict[str, str]) -> dict:
    """CSS custom properties → W3C Design Tokens format, grouped by kind."""
    groups: dict[str, dict] = {}

    def put(group: str, name: str, type_: str, value: str):
        groups.setdefault(group, {})[name] = {"$type": type_, "$value": value}

    for var, value in tokens.items():
        name = var.removeprefix("--")
        if name.startswith("color-"):
            put("color", name.removeprefix("color-"), "color", value)
        elif name.startswith(("font-", "ff-")) and ("," in value or '"' in value or "'" in value):
            put("fontFamily", name.split("-", 1)[1], "fontFamily", value)
        elif name.startswith(("text-", "fs-", "font-size")):
            put("fontSize", name.split("-", 1)[1], "dimension", value)
        elif name.startswith(("space-", "spacing-", "gap-")):
            put("spacing", name.split("-", 1)[1], "dimension", value)
        elif name.startswith("radius"):
            put("radius", name.removeprefix("radius-") or "base", "dimension", value)
        elif name.startswith("shadow"):
            put("shadow", name.removeprefix("shadow-") or "base", "shadow", value)
        elif name.startswith(("duration", "dur-")):
            put("duration", name.split("-", 1)[-1], "duration", value)
        elif name.startswith(("ease", "easing")):
            put("easing", name.split("-", 1)[-1], "cubicBezier", value)
        else:
            put("other", name, "string", value)
    return groups


async def build_handoff(state: AgentState) -> dict:
    root = run_dir(state["run_id"])
    out = root / "output"
    if out.exists():
        shutil.rmtree(out)
    (out / "screenshots").mkdir(parents=True)
    (out / "history").mkdir()
    best = state["best"]
    html = (root / best["html_path"]).read_text()
    (out / "index.html").write_text(html)
    for vp, p in (best.get("screenshots") or {}).items():
        shutil.copyfile(root / p, out / "screenshots" / f"{vp}.png")
    for f in sorted((root / "refine").glob("v*.html")) + sorted((root / "refine").glob("v*-review.json")):
        shutil.copyfile(f, out / "history" / f.name)
    tokens = root_tokens(html)
    dump_json(out / "tokens.json", w3c_tokens(tokens))
    remaining = [i for i in state.get("issues") or [] if i["status"] in ("open", "regressed")]
    dump_json(out / "review-report.json", {
        "final_version": best["version"], "final_score": best.get("score"),
        "scores": (best.get("review") or {}).get("scores"), "audit": best.get("audit"),
        "stop_reason": state.get("stop_reason"), "iterations": state.get("iteration"),
        "trajectory": [{"version": h["version"], "score": h["score"]} for h in state.get("history") or []],
        "remaining_issues": remaining, "usage": state.get("usage"),
    })
    components = list(dict.fromkeys(re.findall(r'data-component="([^"]+)"', html)))
    content = "\n\n".join([
        f"<final_html>\n{html}\n</final_html>",
        f"<style_spec>\n{json.dumps(state.get('style_lock'), indent=1)}\n</style_spec>",
        f"<remaining_issues>\n{json.dumps(remaining, indent=1)}\n</remaining_issues>",
        f"<components>{', '.join(components)}</components>",
    ])
    usage: dict = {}
    try:
        text, usage = await get_llm().text(
            "handoff", system=settings.prompt("handoff"), content=content,
            mock=lambda: mock.handoff(components, tokens, state.get("style_lock") or {}, best.get("review")),
        )
    except LLMError as e:
        text = mock.handoff(components, tokens, state.get("style_lock") or {}, best.get("review")) + f"\n\n> HANDOFF generation failed: {e}\n"
    (out / "HANDOFF.md").write_text(text)
    emit("handoff_built", files=sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()))
    return {"handoff_dir": "output", "usage": usage}


async def export(state: AgentState) -> dict:
    root = run_dir(state["run_id"])
    out = root / "output"
    if settings.config().get("export_pdf"):
        try:
            await get_browser().pdf(out / "index.html", out / "design.pdf", 1440)
            await get_browser().pdf(out / "index.html", out / "design-mobile.pdf", 375)
        except Exception as e:  # PDF is optional
            emit("pdf_failed", error=str(e))
    zpath = root / "handoff.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))
    emit("exported", zip="handoff.zip", pdf=(out / "design.pdf").exists())
    return {}
