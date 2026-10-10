"""A6 console errors (and basic document validity), A8 integrability."""

from __future__ import annotations

import re

from ...state import CheckResult

TOKEN_PROPS = {
    "color", "background", "background-color", "border-color", "outline-color", "fill", "stroke",
    "border", "border-top", "border-bottom", "border-left", "border-right",
    "font-family", "font-size",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right", "margin-inline", "margin-block",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right", "padding-inline", "padding-block",
    "gap", "row-gap", "column-gap",
}
LITERAL_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\(")
LITERAL_LENGTH = re.compile(r"(?<![\w.-])(?:\d*\.)?\d+(?:px|rem|em)\b")
TRIVIAL_LENGTH = re.compile(r"^(?:0|1px|2px|0\.5px)$")


def _style_blocks(html: str) -> str:
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S | re.I))
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def token_usage(html: str) -> tuple[int, int, list[str]]:
    """Return (tokenized, total, examples of literal declarations)."""
    css = _style_blocks(html)
    tokenized = total = 0
    literals: list[str] = []
    for prop, value in re.findall(r"([a-zA-Z-]+)\s*:\s*([^;{}]+?)\s*(?=;|})", css):
        prop = prop.lower()
        if prop.startswith("--") or prop not in TOKEN_PROPS:
            continue
        v = value.strip()
        uses_var = "var(--" in v
        lengths = [l for l in LITERAL_LENGTH.findall(v) if not TRIVIAL_LENGTH.match(l)]
        has_literal = bool(LITERAL_COLOR.search(v)) or (prop == "font-family" and not uses_var) or bool(lengths)
        if not uses_var and not has_literal:
            continue  # auto / inherit / 0 / transparent / percentages: not a design decision
        total += 1
        if uses_var and not LITERAL_COLOR.search(v):
            tokenized += 1
        elif len(literals) < 8:
            literals.append(f"{prop}: {v}")
    return tokenized, total, literals


def a6_console(render: dict, html: str) -> CheckResult:
    items = [{"error": e} for e in render["console_errors"]]
    low = html.lower()
    if "<!doctype html" not in low[:200]:
        items.append({"error": "missing <!doctype html>"})
    if not re.search(r"<html[^>]*\blang=", low):
        items.append({"error": "<html> has no lang attribute"})
    if "<meta name=\"viewport\"" not in low and "<meta name='viewport'" not in low:
        items.append({"error": "missing <meta name=\"viewport\">"})
    return CheckResult(
        id="A6", name="HTML validity, console errors", passed=not items,
        details=f"{len(items)} problem(s)" if items else "No console errors; document basics present",
        items=items[:10],
    )


def a8_integrability(render: dict, html: str) -> CheckResult:
    desktop = render["facts"].get("desktop") or next(iter(render["facts"].values()))
    items = []
    if desktop["inline_style_count"]:
        items.append({"problem": f"{desktop['inline_style_count']} inline style= attribute(s)", "examples": desktop["inline_styles"][:5]})
    tok, total, literals = token_usage(html)
    ratio = tok / total if total else 1.0
    if ratio < 0.9:
        items.append({"problem": f"only {ratio:.0%} of color/font/spacing values use var(--*) tokens (need ≥ 90%)",
                      "examples": literals})
    if desktop["missing_component"]:
        items.append({"problem": "top-level blocks without data-component", "examples": desktop["missing_component"]})
    if desktop["h1_count"] != 1:
        items.append({"problem": f"page has {desktop['h1_count']} <h1> elements (need exactly 1)"})
    if render["blocked_requests"]:
        items.append({"problem": "network requests outside the allowlist", "examples": render["blocked_requests"][:5]})
    return CheckResult(
        id="A8", name="Integrability", passed=not items,
        details=(f"{len(items)} problem(s); token usage {ratio:.0%}" if items else f"Token usage {ratio:.0%}; structure is integration-ready"),
        items=items,
    )
