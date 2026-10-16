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


def key_page_id(state: dict) -> str:
    """The entry page of flow 1. It is designed first, and its tokens and shell bind every other page."""
    return state["intake"]["pages"][0]["id"]


def page_spec(state: dict, page_id: str) -> dict:
    return next(p for p in state["intake"]["pages"] if p["id"] == page_id)


def page_links(state: dict, page_id: str) -> dict:
    """Files this page must link to (its flow steps and links_to), and every file in the site."""
    files = {p["id"]: p["file"] for p in state["intake"]["pages"]}
    return {"required": [files[l] for l in page_spec(state, page_id)["links_to"] if l in files],
            "known": list(files.values())}


def shots_dir(html_path: str) -> str:
    """pages/home/v3.html -> pages/home/v3-shots"""
    return html_path.removesuffix(".html") + "-shots"


def review_path(html_path: str) -> str:
    """pages/home/v3.html -> pages/home/v3-review.json"""
    return html_path.removesuffix(".html") + "-review.json"


def lock_tokens(html: str, locked: dict[str, str]) -> tuple[str, list[str]]:
    """Give the page's first `:root` block the key page's token values, adding any it lacks. The page may keep
    extra tokens of its own. Returns the new HTML and the names that changed."""
    m = next((m for m in re.finditer(r"(:root\s*\{)(.*?)(\})", html, flags=re.S)), None)
    if not m or not locked:
        return html, []
    body, changed = m.group(2), []
    seen = set()

    def swap(d: re.Match) -> str:
        name, value = d.group(1), d.group(2).strip()
        seen.add(name)
        if name in locked and value != locked[name]:
            changed.append(name)
            return f"{name}: {locked[name]};"
        return d.group(0)

    body = re.sub(r"(--[\w-]+)\s*:\s*([^;]+);", swap, body)
    missing = [n for n in locked if n not in seen]
    if missing:
        body = body.rstrip() + "\n  /* Locked from the key page */\n" + "".join(f"  {n}: {locked[n]};\n" for n in missing)
        changed += missing
    return html[:m.start(2)] + body + html[m.end(2):], changed


def put_first_in_head(html: str, marker: str, css: str) -> str:
    """Make `<style marker>css</style>` the first thing in <head>, replacing any earlier copy."""
    block = f"<style {marker}>\n{css}</style>"
    html = re.sub(rf"<style {marker}>.*?</style>\s*", "", html, flags=re.S)
    html, n = re.subn(r"(<head[^>]*>)", lambda m: f"{m.group(1)}\n{block}", html, count=1, flags=re.I)
    if not n:
        html = re.sub(r"(<html[^>]*>)", lambda m: f"{m.group(1)}\n<head>{block}</head>", html, count=1, flags=re.I)
    return html


def with_base_layer(html: str) -> str:
    """The structural defaults every full design starts from (prompts/base_layer.css)."""
    return put_first_in_head(html, "data-base-layer", (settings.ROOT / "prompts" / "base_layer.css").read_text())


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
        "page_id": design.get("page_id"),
        "version": design["version"],
        "html_path": design["html_path"],
        "screenshots": design.get("screenshots", {}),
        "score": design.get("score"),
        "scores": review.get("scores", []),
        "issues": review.get("issues", []),
        "summary": review.get("summary"),
        "audit": {"passed": audit.get("passed"),
                  "checks": [{"id": c["id"], "name": c["name"], "passed": c["passed"],
                                     "blocking": c.get("blocking", True), "details": c["details"]}
                             for c in audit.get("checks", [])]},
        "executor_summary": design.get("executor_summary"),
    }


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
