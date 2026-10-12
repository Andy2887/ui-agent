"""Layer A: deterministic gates (plan §6.1). Pure code, no LLM."""

from __future__ import annotations

from ...state import AuditResult
from .a11y import a1_axe, a2_contrast, a7_focus
from .integrity import a6_console, a8_integrability, token_usage
from .layout import a3_overflow, a4_tap_targets, a5_font_floor, a9_balance


def run_layer_a(render: dict, html: str) -> AuditResult:
    checks = [
        a1_axe(render), a2_contrast(render), a3_overflow(render), a4_tap_targets(render),
        a5_font_floor(render), a6_console(render, html), a7_focus(render), a8_integrability(render, html), a9_balance(render),
    ]
    return AuditResult(passed=all(c.passed or not c.blocking for c in checks), checks=checks)


__all__ = ["run_layer_a", "token_usage"]
