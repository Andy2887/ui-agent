"""Rendering: full designs with the Layer-A audit (plan §4.8)."""

from __future__ import annotations

from ..tools.autofix import apply_font_floor
from ..tools.browser import get_browser
from ..tools.checks import detect_slop, run_layer_a
from .common import dump_json, emit, rel, run_dir


def dom_summary(render: dict) -> dict:
    """What the reviewer gets alongside the screenshots."""
    out = {}
    for vp, f in render["facts"].items():
        out[vp] = {
            "page_height": f["page_height"], "body_font_px": f["body_font_px"], "body_font_family": f["body_font_family"],
            "h1_count": f["h1_count"], "headings": f["headings"], "components": f["components"],
            "root_custom_properties": f["root_custom_properties"],
        }
    return out


async def render_design(run_id: str, design: dict, out_subdir: str, links: dict | None = None) -> tuple[dict, dict]:
    """Render `design["html_path"]`, attach screenshots/tiles/audit, persist facts. Returns (design, render).
    `links`: what the page must link to in the site (common.page_links), for A11."""
    root = run_dir(run_id)
    html_path = root / design["html_path"]
    out_dir = root / out_subdir
    render = await get_browser().render(html_path, out_dir)
    audit = run_layer_a(render, html_path.read_text(), await detect_slop(html_path), links)
    autofixes: list[dict] = []
    if render["font_floor_rules"] and not next(c for c in audit.checks if c.id == "A5").passed:
        html, autofixes = apply_font_floor(html_path.read_text(), render["font_floor_rules"])
        if autofixes:  # code-side A5 fix: no LLM round for text that is simply set too small
            html_path.write_text(html)
            render = await get_browser().render(html_path, out_dir)
            audit = run_layer_a(render, html, await detect_slop(html_path), links)
            emit("autofix", version=design.get("version"), check="A5", fixes=autofixes)
    dump_json(out_dir / "render.json", {k: v for k, v in render.items() if k not in ("screenshots", "tiles")})
    design = {
        **design,
        "screenshots": {vp: rel(run_id, p) for vp, p in render["screenshots"].items()},
        "tiles": {vp: [rel(run_id, p) for p in ps] for vp, ps in render["tiles"].items()},
        "audit": audit.model_dump(),
    }
    if autofixes:
        design["autofixes"] = autofixes
    return design, render

