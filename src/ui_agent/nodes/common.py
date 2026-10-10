"""Helpers shared by nodes: run paths, events, design snapshots, image blocks."""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

from langgraph.config import get_stream_writer

from .. import settings

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def run_dir(run_id: str) -> Path:
    p = settings.runs_dir() / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def rel(run_id: str, path: Path | str) -> str:
    return str(Path(path).resolve().relative_to(run_dir(run_id).resolve()))


def emit(event_type: str, **data) -> None:
    """Custom stream event; the API relays it to the frontend over SSE."""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    writer({"type": event_type, "ts": time.time(), **data})


def image_block(path: Path) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(path.read_bytes()).decode()}}


def extract_html(text: str) -> str:
    m = re.search(r"```(?:html)?\s*(<!doctype html.*?</html>)\s*```", text, flags=re.S | re.I)
    if m:
        return m.group(1)
    m = re.search(r"<!doctype html.*</html>", text, flags=re.S | re.I)
    if m:
        return m.group(0)
    raise ValueError("model output did not contain a complete HTML document")


def root_tokens(html: str) -> dict[str, str]:
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S | re.I))
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    tokens: dict[str, str] = {}
    for block in re.findall(r":root\s*\{(.*?)\}", css, flags=re.S):
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block):
            tokens.setdefault(name, value.strip())
    return tokens


def weighted_score(scores: list[dict]) -> float:
    weights = {c["id"]: c["weight"] for c in settings.rubric()["layer_b"]}
    total = sum(weights.get(s["criterion"], 1.0) for s in scores)
    if not total:
        return 0.0
    return round(sum(s["score"] * weights.get(s["criterion"], 1.0) for s in scores) / total, 2)


def rubric_text() -> str:
    lines = []
    for c in settings.rubric()["layer_b"]:
        lines.append(f"### {c['id']} {c['name']} (weight {c['weight']})")
        for k, v in c["anchors"].items():
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def pref_summary(prefs: dict) -> dict:
    """Explicit choices only (what's fixed), with preset details the models need."""
    out: dict = {}
    if prefs.get("styles"):
        out["styles"] = [{"id": s, **{k: v for k, v in (settings.style(s) or {}).items() if k in ("name", "guidance")}}
                         for s in prefs["styles"]]
    if prefs.get("layouts"):
        out["layouts"] = [{"id": l, **{k: v for k, v in (settings.layout(l) or {}).items() if k in ("name", "brief")}}
                          for l in prefs["layouts"]]
    color = prefs.get("color")
    if color and color.get("kind") == "direction":
        d = settings.color_direction(color["value"]) or {}
        out["color_direction"] = {"id": color["value"], "name": d.get("name"), "ranges_oklch": d.get("ranges"),
                                  "example_palettes": d.get("examples")}
    elif color and color.get("kind") == "brand":
        out["brand_color"] = color["value"]
    out["theme"] = prefs.get("theme", "light")
    if prefs.get("typography"):
        t = settings.typography(prefs["typography"]) or {}
        out["typography"] = {"id": prefs["typography"], "heading": t.get("heading"), "body": t.get("body"),
                             "scale_ratio": t.get("scale_ratio")}
    for group, key in (("density", "density"), ("shapes", "shape"), ("motion", "motion"), ("imagery", "imagery")):
        if prefs.get(key):
            out[key] = settings.option(group, prefs[key])
    for k in ("product_name", "product_description", "tone", "sections"):
        if prefs.get(k):
            out[k] = prefs[k]
    if prefs.get("copy_text") or prefs.get("copy"):
        out["copy"] = prefs.get("copy_text") or prefs.get("copy")
    return out


def open_axes(prefs: dict) -> list[str]:
    axes = []
    if not prefs.get("styles"):
        axes.append("reference style")
    if not prefs.get("layouts"):
        axes.append("layout archetype")
    if not prefs.get("color"):
        axes.append("palette / color direction")
    elif prefs["color"].get("kind") == "direction":
        axes.append("exact palette within the color direction")
    if not prefs.get("typography"):
        axes.append("type pairing")
    for k in ("density", "shape", "motion", "imagery"):
        if not prefs.get(k):
            axes.append(k)
    return axes


def design_snapshot(design: dict) -> dict:
    """Compact per-iteration record for history/timeline (no raw facts)."""
    review = design.get("review") or {}
    audit = design.get("audit") or {}
    return {
        "version": design["version"],
        "html_path": design["html_path"],
        "screenshots": design.get("screenshots", {}),
        "score": design.get("score"),
        "scores": review.get("scores", []),
        "issues": review.get("issues", []),
        "summary": review.get("summary"),
        "audit": {"passed": audit.get("passed"),
                  "checks": [{"id": c["id"], "name": c["name"], "passed": c["passed"], "details": c["details"]}
                             for c in audit.get("checks", [])]},
        "executor_summary": design.get("executor_summary"),
    }


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
