"""M0: each Layer-A check catches its seeded defect and passes the clean fixture."""

import asyncio
import re
from pathlib import Path

import pytest

from ui_agent import mock
from ui_agent.tools.browser import get_browser
from ui_agent.tools.checks import run_layer_a

INTAKE = mock.intake({"problem": "Shipfast: deploys break too often", "audience": "small dev teams"}, []).model_dump()
BRIEF = mock.plan(1, INTAKE, ["neutral"]).briefs[0]
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
                res[name] = run_layer_a(await get_browser().render(p, out / name), html)
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
    check = next(c for c in results[name].checks if c.id == expected)
    assert not check.passed, f"{expected} did not catch its defect"


def test_balance_is_a_warning_not_a_gate(results):
    audit = results["A9"]
    a9 = next(c for c in audit.checks if c.id == "A9")
    assert not a9.blocking and a9.items[0]["kind"] == "short-column"
    assert audit.passed, [c.id for c in audit.failing()]


def test_empty_style_attribute_is_not_an_inline_style(results):
    a8 = next(c for c in results["input"].checks if c.id == "A8")
    assert a8.passed, a8.items


def test_token_usage_counts_literals():
    from ui_agent.tools.checks import token_usage
    tok, total, lit = token_usage("<style>:root{--c:#fff} .a{color:var(--c);padding:24px;margin:0;background:#000}</style>")
    assert (tok, total) == (1, 3) and any("24px" in l for l in lit)
