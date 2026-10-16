"""A11 flow links: every flow step that moves to another page has a real link to it, and no link points at a
page the site doesn't have. Static HTML check; the pages link to each other by file name."""

from __future__ import annotations

import re

from ...state import CheckResult

HREF = re.compile(r"""<(?:a|form)\b[^>]*?\b(?:href|action)\s*=\s*["']([^"'#?]*)""", re.I)


def page_hrefs(html: str) -> set[str]:
    """Same-site page targets: relative paths ending in .html, without ./ or a leading slash."""
    out = set()
    for h in HREF.findall(html):
        h = h.strip()
        if not h or re.match(r"^[a-z]+:", h, flags=re.I) or h.startswith("//"):
            continue
        out.add(h.removeprefix("./").lstrip("/"))
    return {h for h in out if h.endswith(".html")}


def a11_flow_links(html: str, links: dict | None) -> CheckResult | None:
    """`links`: {"required": files this page must link to, "known": every file in the site}. None skips A11."""
    if links is None:
        return None
    found = page_hrefs(html)
    items = [{"missing_link_to": f} for f in links["required"] if f not in found]
    items += [{"link_to_unknown_page": f} for f in sorted(found - set(links["known"]))]
    return CheckResult(
        id="A11", name="Flow links", passed=not items,
        details="every flow step links to its next page" if not items else
        f"{sum('missing_link_to' in i for i in items)} missing, {sum('link_to_unknown_page' in i for i in items)} to unknown pages",
        items=items,
        fix="Add a real <a href=\"<file>\"> (or a form action) for every missing link, on the button or link the flow "
            "step uses. Point links to unknown pages at a file in the site map, or remove them.",
    )
