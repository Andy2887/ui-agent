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
