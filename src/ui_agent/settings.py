"""Loads config.yaml, rubric.yaml, presets/*.json and prompts/*.md from the project root."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("UI_AGENT_ROOT", Path(__file__).resolve().parents[2]))


@lru_cache
def config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


@lru_cache
def rubric() -> dict:
    return yaml.safe_load((ROOT / "rubric" / "rubric.yaml").read_text())


@lru_cache
def presets() -> dict:
    out = {}
    for name in ("styles", "layouts", "colors", "typography", "options"):
        out[name] = json.loads((ROOT / "presets" / f"{name}.json").read_text())
    return out


@lru_cache
def prompt(name: str) -> str:
    return (ROOT / "prompts" / f"{name}.md").read_text()


def mock_mode() -> bool:
    """UI_AGENT_MOCK=1 swaps every LLM call for a deterministic offline stand-in."""
    return os.environ.get("UI_AGENT_MOCK", "").lower() in ("1", "true", "yes")


def runs_dir() -> Path:
    p = Path(os.environ["UI_AGENT_RUNS_DIR"]) if os.environ.get("UI_AGENT_RUNS_DIR") else ROOT / config()["runs_dir"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    p = ROOT / config()["data_dir"]
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- preset lookups -------------------------------------------------------

def style(style_id: str) -> dict | None:
    return next((s for s in presets()["styles"]["styles"] if s["id"] == style_id), None)


def layout(layout_id: str) -> dict | None:
    return next((l for l in presets()["layouts"]["layouts"] if l["id"] == layout_id), None)


def color_direction(direction_id: str) -> dict | None:
    return next((c for c in presets()["colors"]["directions"] if c["id"] == direction_id), None)


def typography(typo_id: str) -> dict | None:
    return next((t for t in presets()["typography"]["pairings"] if t["id"] == typo_id), None)


def option(group: str, option_id: str) -> dict | None:
    return next((o for o in presets()["options"][group] if o["id"] == option_id), None)


def page_type(pt_id: str) -> dict | None:
    return next((p for p in presets()["layouts"]["page_types"] if p["id"] == pt_id), None)


def section(section_id: str) -> dict | None:
    return next((s for s in presets()["layouts"]["sections"] if s["id"] == section_id), None)
