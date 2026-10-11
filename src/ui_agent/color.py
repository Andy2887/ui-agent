"""Color math: hex <-> OKLCH, WCAG contrast, palette checks and repair (plan §4.4, §5.4)."""

from __future__ import annotations

import math

# Role pairs checked for WCAG AA. (foreground, background, minimum ratio)
CONTRAST_PAIRS: list[tuple[str, str, float]] = [
    ("text", "bg", 4.5),
    ("text", "surface", 4.5),
    ("muted", "bg", 4.5),
    ("muted", "surface", 4.5),
    ("on_primary", "primary", 4.5),
    ("primary", "bg", 3.0),  # buttons / UI components vs. page (WCAG 1.4.11)
    ("accent", "bg", 3.0),
]

PALETTE_ROLES = ["bg", "surface", "text", "muted", "primary", "on_primary", "accent", "border"]


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def relative_luminance(hex_color: str) -> float:
    r, g, b = (_to_linear(c) for c in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hex_to_oklch(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in hex_to_rgb(hex_color))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.hypot(A, B)
    H = math.degrees(math.atan2(B, A)) % 360
    return L, C, H


def _oklch_to_linear_rgb(L: float, C: float, H: float) -> tuple[float, float, float]:
    A = C * math.cos(math.radians(H))
    B = C * math.sin(math.radians(H))
    l_ = L + 0.3963377774 * A + 0.2158037573 * B
    m_ = L - 0.1055613458 * A - 0.0638541728 * B
    s_ = L - 0.0894841775 * A - 1.2914855480 * B
    l, m, s = l_**3, m_**3, s_**3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def oklch_to_hex(L: float, C: float, H: float) -> str:
    """Convert to hex, reducing chroma until the color fits in sRGB."""
    c = C
    for _ in range(40):
        rgb = _oklch_to_linear_rgb(L, c, H)
        if all(-1e-4 <= v <= 1 + 1e-4 for v in rgb):
            break
        c *= 0.92
    return rgb_to_hex(tuple(_from_linear(max(0.0, min(1.0, v))) for v in rgb))  # type: ignore[arg-type]


def hue_in_range(h: float, rng: list[float] | tuple[float, float]) -> bool:
    lo, hi = rng
    if hi - lo >= 360:
        return True
    lo, hi, h = lo % 360, hi % 360, h % 360
    return lo <= h <= hi if lo <= hi else (h >= lo or h <= hi)


def check_palette(palette: dict[str, str]) -> list[dict]:
    """Return failing contrast pairs as dicts: {fg, bg, ratio, required}."""
    failures = []
    for fg, bg, req in CONTRAST_PAIRS:
        if fg in palette and bg in palette:
            ratio = contrast_ratio(palette[fg], palette[bg])
            if ratio < req:
                failures.append({"fg": fg, "bg": bg, "ratio": round(ratio, 2), "required": req})
    return failures


def _shift_until(color: str, against: str, required: float) -> str:
    """Shift OKLCH lightness of `color` (same hue) until it meets `required` vs `against`."""
    L, C, H = hex_to_oklch(color)
    darker_bg = relative_luminance(against) < 0.18
    step = 0.01 if darker_bg else -0.01
    best = color
    for _ in range(100):
        L = max(0.0, min(1.0, L + step))
        best = oklch_to_hex(L, C, H)
        if contrast_ratio(best, against) >= required:
            return best
    return best


def repair_palette(palette: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Fix failing pairs by shifting the foreground's lightness within its hue.

    Returns (repaired palette, list of human-readable change notes)."""
    fixed = dict(palette)
    notes: list[str] = []
    for _ in range(3):
        failures = check_palette(fixed)
        if not failures:
            break
        for f in failures:
            fg, bg, req = f["fg"], f["bg"], f["required"]
            # Never move the backgrounds; for on_primary/primary, move the button color.
            target = "primary" if fg == "on_primary" else fg
            against = fixed["on_primary"] if fg == "on_primary" else fixed[bg]
            before = fixed[target]
            fixed[target] = _shift_until(before, against, req)
            if fixed[target] != before:
                notes.append(
                    f"{target} {before} → {fixed[target]} to reach {req}:1 contrast against {bg if fg != 'on_primary' else 'on_primary'}"
                )
    return fixed, notes


def palette_matches_direction(palette: dict[str, str], direction: dict) -> list[str]:
    """Check primary/accent hue and chroma against a color direction's ranges."""
    problems = []
    ranges = direction.get("ranges") or {}
    for role in ("primary", "accent"):
        hue_key = f"{role}_hue"
        if role not in palette or hue_key not in ranges:
            continue
        L, C, H = hex_to_oklch(palette[role])
        if C < 0.03:  # near-gray: hue is meaningless; only allowed if the direction permits it
            if not ranges.get("allow_neutral_" + role, False):
                problems.append(f"{role} {palette[role]} is nearly gray, but the direction expects a {role} hue")
            continue
        if not any(hue_in_range(H, r) for r in ranges[hue_key]):
            problems.append(f"{role} {palette[role]} hue {H:.0f}° is outside {ranges[hue_key]}")
        cmin, cmax = ranges.get("chroma", [0, 0.4])
        if not (cmin - 0.02 <= C <= cmax + 0.02):
            problems.append(f"{role} {palette[role]} chroma {C:.2f} is outside {cmin}–{cmax}")
    return problems

