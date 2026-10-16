"""A10 AI-template tells (warning): the deterministic detector from impeccable (github.com/pbakaus/impeccable,
Apache-2.0), limited to template habits no direction asks for. Rules about palette, fonts and effects
(overused fonts, purple gradients, glows, gradient text, marquees) are left out: a style recipe may call
for them, and the reviewer must not override the direction.

The detector is an external binary. When it isn't installed the check is skipped, never failed."""

from __future__ import annotations

import asyncio
import functools
import json
import os
import shutil
import subprocess
from pathlib import Path

from ... import settings
from ...state import CheckResult

# Rule id → what to do instead (shared with the generator's refuse list in prompts/generator.md).
TEMPLATE_HABITS = {
    "hero-eyebrow-chip": "delete the small label or chip above the headline; the headline carries its own weight",
    "kicker-above-heading": "delete the tracked uppercase label above the heading",
    "numbered-section-labels": "drop the 01/02/03 section numbers unless the order matters to the reader",
    "icon-tile-stack": "drop the rounded icon tile above each card heading: put the icon beside the heading, or use a number, an image or nothing",
    "nested-cards": "flatten cards inside cards; separate with spacing, type and dividers",
    "side-tab": "remove the thick colored border on one side of the card; use a hairline border, a tint or nothing",
    "border-accent-on-rounded": "remove the thick accent border from the rounded element, or its radius",
    "gpt-thin-border-wide-shadow": "give the row of cards a hairline border or a shadow, not both",
    "monotonous-spacing": "vary spacing: tight inside groups, generous between sections",
    "flat-type-hierarchy": "make at least one heading step clearly bigger than body text (1.25x or more)",
    "extreme-negative-tracking": "loosen letter-spacing to -0.04em or more",
    "bounce-easing": "replace bounce or elastic easing with an ease-out curve",
    "pulsing-dot": "make the decorative pulsing dot static",
    "shape-assembled-illustration": "replace the SVG scene built from primitive shapes with an annotated data-placeholder",
    "marketing-buzzword": "replace the buzzword with what the product actually does for these users",
    "aphoristic-cadence": "rewrite the 'X. No Y.' one-liners as plain statements",
    "theater-slop-phrase": "say plainly what the thing does instead of calling something 'theater'",
}


def _probe(path: str) -> bool:
    try:
        out = subprocess.run([path, "engine-probe"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and out.stdout.startswith("impeccable-engine")


@functools.cache
def find_engine() -> str | None:
    """`impeccable_bin` in config.yaml or $IMPECCABLE_BIN, else `impeccable` on PATH, else the newest engine the
    impeccable launcher cached in ~/.impeccable/bin. Set either to "off" to disable the check."""
    configured = os.environ.get("IMPECCABLE_BIN") or settings.config().get("impeccable_bin")
    if configured:
        return None if configured == "off" or not _probe(configured) else configured
    cached = sorted(Path.home().glob(".impeccable/bin/*/impeccable"), key=lambda p: [int(x) if x.isdigit() else 0
                                                                                      for x in p.parent.name.split(".")])
    for candidate in [shutil.which("impeccable"), *map(str, reversed(cached))]:
        if candidate and _probe(candidate):
            return candidate
    return None


async def detect_slop(html_path: Path) -> list[dict] | None:
    """The detector's findings for one HTML file, or None when it could not run."""
    engine = find_engine()
    if not engine:
        return None
    proc = await asyncio.create_subprocess_exec(engine, "detect", "--json", "--no-config", str(html_path),
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    if proc.returncode not in (0, 2):  # 2 = scan completed with findings
        return None
    try:
        return json.loads(out or b"[]")
    except json.JSONDecodeError:
        return None


def a10_slop(findings: list[dict] | None) -> CheckResult:
    if findings is None:
        return CheckResult(id="A10", name="AI-template tells", passed=True, blocking=False,
                           details="Skipped: the impeccable detector did not run (not installed, or disabled)")
    by_rule: dict[str, list[dict]] = {}
    for f in findings:
        if f.get("antipattern") in TEMPLATE_HABITS:
            by_rule.setdefault(f["antipattern"], []).append(f)
    items = [{"rule": rule, "count": len(fs), "where": fs[0].get("snippet", "")[:100]} for rule, fs in by_rule.items()]
    return CheckResult(
        id="A10", name="AI-template tells", passed=not items, blocking=False,
        details=(f"{len(items)} template habit(s): " + ", ".join(f"{i['rule']} ×{i['count']}" for i in items) if items
                 else "No template habits found"),
        items=items,
        fix="; ".join(f"{rule}: {TEMPLATE_HABITS[rule]}" for rule in by_rule),
    )
