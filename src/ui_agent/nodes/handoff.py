"""4.11 build_handoff, 4.12 export: one HTML file per page, shared tokens, flows, screenshots and PDFs."""

from __future__ import annotations

import json
import re
import shutil
import zipfile

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..state import MAX_PAGES, AgentState
from ..tools.browser import get_browser
from .common import dump_json, emit, key_page_id, root_tokens, run_dir


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


def flows_md(state: AgentState) -> str:
    """FLOWS.md: each PM flow in their words, then the pages it walks through. Code-written, so it is exact."""
    intake = state["intake"]
    files = {p["id"]: p for p in intake["pages"]}
    lines = [f"# Flows: {intake.get('product_name', '')}", "",
             "Each flow as the PM described it, then the pages it walks through. Every step that moves to another "
             "page is a real link in the HTML (audit check A11).", ""]
    for i, f in enumerate(intake.get("flows") or [], 1):
        pm = (state["brief"].get("flows") or [])[i - 1:i]
        lines += [f"## {i}. {f['name']}", ""]
        if pm:
            lines += [f"> {pm[0]}", ""]
        for n, st in enumerate(f["steps"], 1):
            page = files.get(st["page"]) or {}
            lines.append(f"{n}. `{page.get('file', st['page'])}` ({page.get('name', st['page'])}): {st['action']}")
        lines.append("")
    lines += ["## Pages", "", "| File | Page | Purpose | Links to |", "|---|---|---|---|"]
    for p in intake["pages"]:
        links = ", ".join(f"`{files[l]['file']}`" for l in p["links_to"] if l in files) or "none"
        lines.append(f"| `{p['file']}` | {p['name']} | {p['purpose']} | {links} |")
    if intake.get("not_designed"):
        lines += ["", f"Not designed (over the {MAX_PAGES}-page limit): {', '.join(intake['not_designed'])}."]
    return "\n".join(lines) + "\n"


async def build_handoff(state: AgentState) -> dict:
    root = run_dir(state["run_id"])
    out = root / "output"
    if out.exists():
        shutil.rmtree(out)
    (out / "screenshots").mkdir(parents=True)
    (out / "history").mkdir()
    saved = state.get("pages") or {}
    pages = [p for p in state["intake"]["pages"] if (saved.get(p["id"]) or {}).get("best")]
    htmls: dict[str, str] = {}
    report: dict = {}
    remaining: list[dict] = []
    for p in pages:
        s = saved[p["id"]]
        best = s["best"]
        # site/ holds the published pages, token-synced to the key page.
        html = (root / "site" / p["file"]).read_text()
        htmls[p["id"]] = html
        (out / p["file"]).write_text(html)
        (out / "screenshots" / p["id"]).mkdir()
        for vp, shot in (best.get("screenshots") or {}).items():
            shutil.copyfile(root / shot, out / "screenshots" / p["id"] / f"{vp}.png")
        (out / "history" / p["id"]).mkdir()
        for f in sorted((root / "pages" / p["id"]).glob("v*.html")) + sorted((root / "pages" / p["id"]).glob("v*-review.json")):
            shutil.copyfile(f, out / "history" / p["id"] / f.name)
        left = [i for i in s.get("issues") or [] if i["status"] in ("open", "regressed")]
        remaining += [{**i, "page": p["file"]} for i in left]
        report[p["file"]] = {
            "final_version": best["version"], "final_score": best.get("score"),
            "scores": (best.get("review") or {}).get("scores"), "audit": best.get("audit"),
            "stop_reason": s.get("stop_reason"), "iterations": s.get("iteration"),
            "trajectory": [{"version": h["version"], "score": h["score"]} for h in state.get("history") or []
                           if h.get("page_id") == p["id"]],
            "remaining_issues": left,
        }
    key = key_page_id(state)
    tokens = root_tokens(htmls.get(key) or next(iter(htmls.values()), ""))
    dump_json(out / "tokens.json", w3c_tokens(tokens))
    (out / "FLOWS.md").write_text(flows_md(state))
    dump_json(out / "review-report.json", {
        "pages": report, "skipped": [pid for pid, s in saved.items() if s.get("skipped")],
        "not_designed": state["intake"].get("not_designed") or [], "usage": state.get("usage"),
    })
    components = {p["file"]: list(dict.fromkeys(re.findall(r'data-component="([^"]+)"', htmls[p["id"]]))) for p in pages}
    content = "\n\n".join([
        f"<flows>\n{flows_md(state)}\n</flows>",
        *(f"<page file=\"{p['file']}\" key=\"{str(p['id'] == key).lower()}\">\n{htmls[p['id']]}\n</page>" for p in pages),
        f"<style_spec>\n{json.dumps(state.get('style_lock'), indent=1)}\n</style_spec>",
        f"<remaining_issues>\n{json.dumps(remaining, indent=1)}\n</remaining_issues>",
        f"<components>\n{json.dumps(components, indent=1)}\n</components>",
    ])
    usage: dict = {}
    spec = state.get("style_lock") or {}
    try:
        text, usage = await get_llm().text(
            "handoff", system=settings.prompt("handoff"), content=content,
            mock=lambda: mock.handoff(components, tokens, spec),
        )
    except LLMError as e:
        text = mock.handoff(components, tokens, spec) + f"\n\n> HANDOFF generation failed: {e}\n"
    (out / "HANDOFF.md").write_text(text)
    emit("handoff_built", files=sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()))
    return {"handoff_dir": "output", "usage": usage}


async def export(state: AgentState) -> dict:
    root = run_dir(state["run_id"])
    out = root / "output"
    if settings.config().get("export_pdf"):
        try:
            (out / "pdf").mkdir(exist_ok=True)
            for p in state["intake"]["pages"]:
                if (out / p["file"]).exists():
                    stem = p["file"].removesuffix(".html")
                    await get_browser().pdf(out / p["file"], out / "pdf" / f"{stem}.pdf", 1440)
                    await get_browser().pdf(out / p["file"], out / "pdf" / f"{stem}-mobile.pdf", 375)
        except Exception as e:  # PDF is optional
            emit("pdf_failed", error=str(e))
    zpath = root / "handoff.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))
    emit("exported", zip="handoff.zip", pdf=(out / "pdf" / "index.pdf").exists())
    return {}
