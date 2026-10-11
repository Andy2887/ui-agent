"""Rendering: sketches (screenshots only), and full designs with the Layer-A audit (plan §4.5, §4.8)."""

from __future__ import annotations

from ..tools.browser import get_browser
from ..tools.checks import run_layer_a
from .common import dump_json, rel, run_dir


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


async def render_design(run_id: str, design: dict, out_subdir: str) -> tuple[dict, dict]:
    """Render `design["html_path"]`, attach screenshots/tiles/audit, persist facts. Returns (design, render)."""
    root = run_dir(run_id)
    html_path = root / design["html_path"]
    out_dir = root / out_subdir
    render = await get_browser().render(html_path, out_dir)
    audit = run_layer_a(render, html_path.read_text())
    dump_json(out_dir / "render.json", {k: v for k, v in render.items() if k not in ("screenshots", "tiles")})
    design = {
        **design,
        "screenshots": {vp: rel(run_id, p) for vp, p in render["screenshots"].items()},
        "tiles": {vp: [rel(run_id, p) for p in ps] for vp, ps in render["tiles"].items()},
        "audit": audit.model_dump(),
    }
    return design, render


async def render_sketch(run_id: str, sketch: dict, out_subdir: str) -> dict:
    """Screenshots only: a low-fi sketch is judged by the person, not by the audit."""
    root = run_dir(run_id)
    render = await get_browser().render(root / sketch["html_path"], root / out_subdir, deep_checks=False)
    return {
        **sketch,
        "screenshots": {vp: rel(run_id, p) for vp, p in render["screenshots"].items()},
        "tiles": {vp: [rel(run_id, p) for p in ps] for vp, ps in render["tiles"].items()},
    }
