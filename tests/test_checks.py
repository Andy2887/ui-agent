"""M0: each Layer-A check catches its seeded defect and passes the clean fixture."""

import asyncio
import re
from pathlib import Path

import pytest

from ui_agent import mock
from ui_agent.nodes.intake import plan_site
from ui_agent.tools.browser import get_browser
from ui_agent.tools.checks import detect_slop, run_layer_a
from ui_agent.tools.checks.slop import find_engine

INTAKE = plan_site(mock.intake({"problem": "Shipfast: deploys break too often", "audience": "small dev teams",
                      "flows": ["A lead lands on the home page and signs up."]}, [])).model_dump()
BRIEF = mock.plan(INTAKE, "neutral")
CLEAN = mock.html_for(BRIEF, INTAKE, defects=[])


def _inject(html: str, css: str = "", body: str = "") -> str:
    return html.replace("</style>", css + "\n</style>").replace("</main>", body + "\n</main>")


FIXTURES = {
    "clean": (CLEAN, None),
    "A1": (_inject(CLEAN, body='<section data-component="x"><h2>Logo</h2><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></section>'), "A1"),
    "A2": (_inject(CLEAN, css=".card__body { color: #d0d0d0; }"), "A2"),
    "A3": (_inject(CLEAN, body='<section data-component="wide"><div class="wide">x</div></section>', css=".wide { width: 900px; }"), "A3"),
    "A4": (mock.html_for(BRIEF, INTAKE, defects=["small-targets"]), "A4"),
    "A5": (mock.html_for(BRIEF, INTAKE, defects=["tiny-text"]), "A5"),
    "A6": (_inject(CLEAN, body="<script>undefinedFunction()</script>"), "A6"),
    "A7": (mock.html_for(BRIEF, INTAKE, defects=["no-focus"]), "A7"),
    "A8": (CLEAN.replace('<section class="cta"', '<section style="padding: 12px" class="cta"', 1), "A8"),
    # A short column beside a tall one leaves a large empty area under it at 1440px.
    "A9": (_inject(CLEAN, css=".split { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6); }",
                   body='<section data-component="split"><div class="split"><div>' + "<p>Long explanatory paragraph that runs on. " * 30
                        + '</p></div><div><p>Short note.</p></div></div></section>'), "A9"),
    # A thick accent border down one side of a rounded card (impeccable's side-tab rule).
    "A10": (_inject(CLEAN, css=".card { border-left: 4px solid var(--color-accent); }"), "A10"),
    # A line that can't wrap at 1440px: it fits at normal text size, and runs off the window when text doubles.
    "A12": (_inject(CLEAN, css=".stat-line { font-size: 2.5rem; } @media (min-width: 1280px) { .stat-line { white-space: nowrap; } }",
                    body='<section data-component="stats"><p class="stat-line">Ninety-eight percent of deploys ship before lunch</p></section>'),
            "A12"),
    # Playwright's full-page screenshot leaves an empty style="" on text inputs; that is not a design defect.
    "input": (_inject(CLEAN, body='<section data-component="signup"><label for="email">Email</label>'
                                  '<input id="email" type="email" name="email"></section>'), None),
}


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    out = tmp_path_factory.mktemp("m0")

    async def run():
        res = {}
        try:
            for name, (html, _) in FIXTURES.items():
                p = out / f"{name}.html"
                p.write_text(html)
                res[name] = run_layer_a(await get_browser().render(p, out / name), html, await detect_slop(p))
        finally:
            await get_browser().close()
        return res

    return asyncio.run(run())


def test_clean_fixture_passes(results):
    failing = [(c.id, c.details) for c in results["clean"].checks if not c.passed]
    assert not failing, failing


@pytest.mark.parametrize("name", [k for k, (_, expected) in FIXTURES.items() if expected])
def test_seeded_defect_is_caught(results, name):
    expected = FIXTURES[name][1]
    if expected == "A10" and not find_engine():
        pytest.skip("impeccable detector not installed")
    check = next(c for c in results[name].checks if c.id == expected)
    assert not check.passed, f"{expected} did not catch its defect"


def test_balance_is_a_warning_not_a_gate(results):
    audit = results["A9"]
    a9 = next(c for c in audit.checks if c.id == "A9")
    assert not a9.blocking and a9.items[0]["kind"] == "short-column"
    assert audit.passed, [c.id for c in audit.failing()]


def test_text_scaling_is_a_warning_not_a_gate(results):
    audit = results["A12"]
    a12 = next(c for c in audit.checks if c.id == "A12")
    assert not a12.blocking and a12.items[-1]["offenders"], a12.items
    assert audit.passed, [c.id for c in audit.failing()]


def test_empty_style_attribute_is_not_an_inline_style(results):
    a8 = next(c for c in results["input"].checks if c.id == "A8")
    assert a8.passed, a8.items


def test_token_usage_counts_literals():
    from ui_agent.tools.checks import token_usage
    tok, total, lit = token_usage("<style>:root{--c:#fff} .a{color:var(--c);padding:24px;margin:0;background:#000}</style>")
    assert (tok, total) == (1, 3) and any("24px" in l for l in lit)
