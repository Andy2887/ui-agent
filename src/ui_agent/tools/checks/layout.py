"""A3 horizontal overflow, A4 tap target size (mobile), A5 font size floor, A9 layout balance (warning),
A12 text scaling (warning)."""

from __future__ import annotations

from ...state import CheckResult


def a3_overflow(render: dict) -> CheckResult:
    items = []
    for vp, f in render["facts"].items():
        if f["scroll_width"] > f["client_width"] + 1:
            items.append({"viewport": vp, "scroll_width": f["scroll_width"], "client_width": f["client_width"],
                          "offenders": f["overflow"]})
    return CheckResult(
        id="A3", name="Horizontal overflow", passed=not items,
        details=("Horizontal scrolling at " + ", ".join(i["viewport"] for i in items)) if items else "No horizontal overflow",
        items=items,
    )


def a4_tap_targets(render: dict) -> CheckResult:
    f = render["facts"].get("mobile")
    if not f:
        return CheckResult(id="A4", name="Tap target size", passed=True, details="No mobile render")
    too_small = [t for t in f["small_targets"] if t["w"] < 24 or t["h"] < 24]
    under_44 = [t for t in f["small_targets"] if t not in too_small]
    return CheckResult(
        id="A4", name="Tap target size", passed=not too_small,
        details=(f"{len(too_small)} target(s) under 24×24px on mobile; {len(under_44)} under the recommended 44×44px"
                 if too_small else f"All targets ≥ 24×24px; {len(under_44)} under the recommended 44×44px"),
        items=[{**t, "level": "fail"} for t in too_small[:10]] + [{**t, "level": "warn"} for t in under_44[:6]],
    )


def a5_font_floor(render: dict) -> CheckResult:
    items = []
    m = render["facts"].get("mobile")
    if m:
        if m["body_font_px"] < 16:
            items.append({"viewport": "mobile", "problem": f"body font-size is {m['body_font_px']}px (< 16px)"})
        for s in m["small_body_text"][:5]:
            items.append({"viewport": "mobile", "selector": s["selector"], "problem": f"body text {s['size']}px (< 16px)"})
    for vp, f in render["facts"].items():
        for t in f["tiny_text"][:5]:
            items.append({"viewport": vp, "selector": t["selector"], "problem": f"{t['size']}px text (< 12px): {t['text']!r}"})
    return CheckResult(
        id="A5", name="Font size floor", passed=not items,
        details=f"{len(items)} font-size problem(s)" if items else "Body ≥ 16px on mobile and nothing under 12px",
        items=items[:12],
    )


def a9_balance(render: dict) -> CheckResult:
    """Warning only: some asymmetry is deliberate (a side rail, a sticky contents list), so the
    reviewer must address it, but it never blocks the audit."""
    items = [{"viewport": vp, **b} for vp in ("desktop", "tablet") for b in (render["facts"].get(vp) or {}).get("balance", [])]
    return CheckResult(
        id="A9", name="Layout balance", passed=not items, blocking=False,
        details=(f"{len(items)} lopsided row(s) or block(s) leave a large empty area" if items
                 else "Side-by-side columns are filled evenly; no block is pushed to one side"),
        items=items[:10],
    )


def a12_text_scale(render: dict) -> CheckResult:
    """Warning only. WCAG 1.4.4 asks that text work at 200%; browser zoom also satisfies it, so this text-only test
    (the root font size doubled at 1440px) is stricter than the standard."""
    t = render.get("text_scale")
    if t is None:
        return CheckResult(id="A12", name="Text scaling", passed=True, blocking=False, details="Not measured")
    items = []
    if t["scale"] < 1.5:
        items.append({"problem": f"body text grew only {t['scale']}x when the reader doubled their text size; "
                                 "font sizes set in px ignore the reader's setting"})
    if t["scroll_width"] > t["viewport_width"] + 1:
        items.append({"problem": f"at 200% text the page is {t['scroll_width'] - t['viewport_width']}px wider than the "
                                 f"{t['viewport_width']}px window", "offenders": t["overflow"]})
    return CheckResult(
        id="A12", name="Text scaling", passed=not items, blocking=False,
        details=("; ".join(i["problem"] for i in items) if items
                 else f"At 200% text the page still fits {t['viewport_width']}px (body text grew {t['scale']}x)"),
        items=items,
        fix="Set font sizes in rem. Let rows wrap when their text grows: flex-wrap on nav and button rows, min-width: 0 "
            "on grid and flex children, max-width: 100% on inputs and media, no fixed widths or white-space: nowrap on text.",
    )
