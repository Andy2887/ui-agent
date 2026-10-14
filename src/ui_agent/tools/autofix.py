"""Deterministic fixes applied after a render, before any LLM sees the page.

A5 font floor: designs often set long secondary text (FAQ answers, form notes) at 13–15px. The browser finds the
rule that sets each such element's size (`FONT_FLOOR_JS`); here that rule's declaration in the source becomes
`font-size: max(1rem, <value>)`, which keeps the designer's value where it is already 16px or more. A rule is
patched only when its text is found exactly once in the design's own CSS; anything ambiguous is left to the
reviewer and executor."""

from __future__ import annotations

import re

STYLE = re.compile(r"(<style(?![^>]*data-base-layer)[^>]*>)(.*?)(</style>)", re.S | re.I)


def _selector_pattern(selector: str) -> str:
    # CSSOM normalizes selectors: spaced combinators, quoted attribute values. Accept the common source spellings.
    selector = re.sub(r"\s*([,>+~])\s*", r"\1", selector.strip())
    out = []
    for ch in selector:
        if ch.isspace():
            out.append(r"\s+")
        elif ch in ",>+~":
            out.append(rf"\s*{re.escape(ch)}\s*")
        elif ch in "\"'":
            out.append(r"[\"']?")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def _norm(value: str) -> str:
    return re.sub(r"(?<![\w.])\.(\d)", r"0.\1", re.sub(r"\s+", "", value.lower()))


def apply_font_floor(html: str, rules: list[dict]) -> tuple[str, list[dict]]:
    """Returns the patched HTML and the rules actually changed."""
    applied: list[dict] = []
    for rule in rules:
        if "max(1rem" in rule["value"]:
            continue
        pattern = re.compile(r"((?:^|[{};]|\*/)\s*" + _selector_pattern(rule["selector"]) + r"\s*\{)([^{}]*)\}")
        hits = []
        for sm in STYLE.finditer(html):
            for m in pattern.finditer(sm.group(2)):
                decl = list(re.finditer(r"font-size\s*:\s*([^;}]+?)\s*(?=;|$)", m.group(2)))
                if decl and _norm(decl[-1].group(1).replace("!important", "")) == _norm(rule["value"]):
                    hits.append((sm.start(2) + m.start(2), decl[-1]))
        if len(hits) != 1:
            continue
        body_start, d = hits[0]
        value = d.group(1)
        important = " !important" if "!important" in value else ""
        new = f"font-size: max(1rem, {value.replace('!important', '').strip()}){important}"
        html = html[:body_start + d.start()] + new + html[body_start + d.end():]
        applied.append({"selector": rule["selector"], "from": value.strip(), "to": new.removeprefix("font-size: "),
                        "size_px": [rule["before"], rule["after"]]})
    return html, applied
