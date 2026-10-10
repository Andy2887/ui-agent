"""A1 accessibility (axe), A2 text contrast (axe color-contrast), A7 focus visibility."""

from __future__ import annotations

from ...state import CheckResult


def a1_axe(render: dict) -> CheckResult:
    bad = [v for v in render["axe"] if v["id"] != "color-contrast" and v.get("impact") in ("serious", "critical")]
    return CheckResult(
        id="A1", name="Accessibility violations", passed=not bad,
        details=f"{len(bad)} serious/critical axe violation(s)" if bad else "No serious or critical axe violations",
        items=[{"rule": v["id"], "impact": v["impact"], "help": v["help"], "viewport": v.get("viewport"),
                "targets": [n["target"] for n in v["nodes"]]} for v in bad],
    )


def a2_contrast(render: dict) -> CheckResult:
    bad = [v for v in render["axe"] if v["id"] == "color-contrast"]
    nodes = [n for v in bad for n in v["nodes"]]
    return CheckResult(
        id="A2", name="Text contrast", passed=not bad,
        details=f"{len(nodes)} element(s) below WCAG AA contrast" if bad else "All text meets WCAG AA contrast",
        items=[{"target": n["target"], "summary": n["summary"]} for n in nodes],
    )


def a7_focus(render: dict) -> CheckResult:
    focus = render["focus"]
    invisible = [f for f in focus if not f["visible"]]
    if not focus:
        return CheckResult(id="A7", name="Focus visibility", passed=True, details="No keyboard-focusable elements found")
    return CheckResult(
        id="A7", name="Focus visibility", passed=not invisible,
        details=(f"{len(invisible)} of {len(focus)} focusable element(s) show no visible focus state"
                 if invisible else f"All {len(focus)} focusable elements show a visible focus state"),
        items=invisible[:12],
    )
