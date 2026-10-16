"""Layer A: deterministic gates (plan §6.1). Pure code, no LLM."""

from __future__ import annotations

from ...state import AuditResult
from .flow import a11_flow_links
from .a11y import a1_axe, a2_contrast, a7_focus
from .integrity import a6_console, a8_integrability, token_usage
from .layout import a3_overflow, a4_tap_targets, a5_font_floor, a9_balance, a12_text_scale
from .slop import a10_slop, detect_slop


def run_layer_a(render: dict, html: str, slop: list[dict] | None = None, links: dict | None = None) -> AuditResult:
    """`slop` is the impeccable detector's output for the same file (detect_slop); None skips A10.
    `links` is what the page must link to in a multi-page site (common.page_links); None skips A11."""
    checks = [
        a1_axe(render), a2_contrast(render), a3_overflow(render), a4_tap_targets(render),
        a5_font_floor(render), a6_console(render, html), a7_focus(render), a8_integrability(render, html), a9_balance(render),
        a10_slop(slop),
    ]
    if (flow := a11_flow_links(html, links)) is not None:
        checks.append(flow)
    checks.append(a12_text_scale(render))
    return AuditResult(passed=all(c.passed or not c.blocking for c in checks), checks=checks)


__all__ = ["detect_slop", "run_layer_a", "token_usage"]
