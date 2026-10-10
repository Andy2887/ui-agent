"""Offline stand-ins for every LLM role (UI_AGENT_MOCK=1).

They exercise the real pipeline end to end: briefs go through the same diversity and
palette checks, generated HTML is rendered and audited for real, the reviewer's issues
come from the real audit, and the executor fixes them through the sandboxed
text-editor handler. Seeded defects are wrapped in `/* defect:<key> */ ... /* /defect */`
markers so the mock executor can repair them with targeted str_replace edits."""

from __future__ import annotations

import html as html_lib
import re

from . import settings
from .color import palette_from_brand
from .state import (
    CriterionScore,
    DirectionBrief,
    IntakeResult,
    Issue,
    Palette,
    PlanResult,
    ReviewResult,
    StyleCharacter,
)

FALLBACK_FONTS = [("Inter", "Inter"), ("Outfit", "DM Sans"), ("Playfair Display", "Source Sans 3"),
                  ("Space Grotesk", "Space Grotesk"), ("Nunito", "Nunito Sans"), ("JetBrains Mono", "IBM Plex Sans")]
NAMES = ["Quiet Precision", "Signal Bold", "Paper & Ink", "Soft Orbit", "Night Shift", "Grid Theory",
         "Warm Welcome", "Blueprint", "Neon Notes", "Open Field"]
REFS = ["swiss", "modern-saas", "editorial", "playful", "technical", "brutalist", "corporate", "luxury"]

# defect key -> (issue id, criterion, severity, selector, viewport, evidence, fix, explanation)
DEFECTS = {
    "no-focus": ("iss_focus_states", "B8", "high", "a, button", "desktop",
                 "A7: links and buttons remove the outline and define no :focus-visible style.",
                 "Add a :focus-visible outline using --color-primary with a 2px offset.",
                 "Keyboard users (and many power users) navigate with Tab. Without a visible focus ring they can't tell where they are on the page."),
    "small-targets": ("iss_mobile_tap_targets", "B5", "high", "[data-component=site-header] .nav__link", "mobile",
                      "A4: nav links are ~18px tall on mobile.",
                      "Give nav links min-height: 44px and inline padding so the tappable area is large enough.",
                      "Fingers are much less precise than a mouse. Small tap targets cause mis-taps, which feel like the site is broken."),
    "literal-values": ("iss_hardcoded_values", "B6", "medium", "[data-component=features] .card", "all",
                       "A8: cards use hard-coded hex colors and pixel paddings instead of tokens.",
                       "Replace literal values with var(--color-surface), var(--color-border) and the spacing scale.",
                       "Tokens keep every component in one visual language and let the next developer change the theme in one place."),
    "tiny-text": ("iss_tiny_footer_text", "B3", "medium", "[data-component=site-footer] .footer__legal", "all",
                  "A5: footer legal text is 11px.",
                  "Use var(--text-sm) (at least 14px) for footer text.",
                  "Text under 12px is hard to read for many people, especially on phones, and looks like an afterthought."),
    "weak-cta": ("iss_hero_cta_weight", "B1", "medium", "[data-component=hero] .btn--primary", "all",
                 "The primary CTA is the same visual weight as the secondary link.",
                 "Give the primary button a filled background and stronger weight; keep the secondary as a ghost button.",
                 "Each screen should have one obvious next step. When two buttons look equal, visitors hesitate and fewer click."),
}
SEEDED = ["no-focus", "small-targets", "literal-values", "tiny-text", "weak-cta"]


# --------------------------------------------------------------------------- intake
def intake(prompt: str, prefs: dict) -> IntakeResult:
    p = prompt.lower()
    page_type = prefs.get("page_type") or next(
        (pt for pt, kws in {"dashboard": ["dashboard", "admin", "analytics"], "pricing": ["pricing"],
                            "auth": ["sign up", "signup", "login", "log in"], "blog": ["blog", "article"],
                            "portfolio": ["portfolio"]}.items() if any(k in p for k in kws)), "landing")
    sections = prefs.get("sections") or settings.page_type(page_type)["default_sections"]
    name = prefs.get("product_name") or (re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", prompt) or ["Acme"])[0]
    return IntakeResult(page_type=page_type, audience="developers and small teams", product_name=name,
                        sections=sections, assumptions=["Audience inferred as developers and small teams (mock)."])


# ---------------------------------------------------------------------------- plan
def plan(n: int, prefs: dict, slots: list[str], layouts_for_slots: list[str | None], attempt: int = 0) -> PlanResult:
    briefs = []
    directions = settings.presets()["colors"]["directions"]
    color = prefs.get("color") or None
    for i in range(n):
        shift = i + attempt * 3
        if color and color["kind"] == "brand":
            light, dark = palette_from_brand(color["value"], "light"), palette_from_brand(color["value"], "dark")
        else:
            d = settings.color_direction(color["value"]) if color else directions[shift % len(directions)]
            ex = d["examples"][i % len(d["examples"])]
            light, dark = ex["light"], ex["dark"]
        typo = settings.typography(prefs["typography"]) if prefs.get("typography") else None
        hf, bf = (typo["heading"]["family"], typo["body"]["family"]) if typo else FALLBACK_FONTS[shift % len(FALLBACK_FONTS)]
        layout_id = layouts_for_slots[i]
        lay = settings.layout(layout_id) if layout_id else None
        ref = prefs["styles"][0] if prefs.get("styles") else REFS[shift % len(REFS)]
        briefs.append(DirectionBrief(
            id=chr(ord("a") + i), name=NAMES[shift % len(NAMES)],
            description=f"A {ref.replace('-', ' ')} take: {(lay['name'] if lay else ('split' if i % 2 else 'centered') + ' hero').lower()}, {(prefs.get('density') or ['airy', 'balanced', 'compact'][shift % 3])} spacing.",
            slot=slots[i], reference_style=ref,
            layout_archetype=lay["brief"] if lay else ["centered hero + 3-up feature grid", "split hero + alternating rows", "screenshot-led hero + bento grid"][shift % 3],
            layout_id=layout_id, heading_font=hf, body_font=bf,
            palette=Palette(**light), dark_palette=Palette(**dark),
            density=prefs.get("density") or ["airy", "balanced", "compact"][shift % 3],
            shape=prefs.get("shape") or ["soft", "sharp", "rounded"][shift % 3],
            motion=prefs.get("motion") or "subtle",
            imagery=prefs.get("imagery") or ["abstract", "illustrations", "photos", "none"][shift % 4],
            signature_element=["oversized numeral section markers", "gradient glow behind the product frame",
                               "hairline grid overlay", "hand-drawn underline on the headline",
                               "terminal-style code card"][shift % 5],
            avoid=["stock-photo clichés", "more than one accent color"],
        ))
    return PlanResult(briefs=briefs)


# ---------------------------------------------------------------------------- html
def _defect(key: str, bad_css: str, enabled: bool, good_css: str) -> str:
    return f"/* defect:{key} */\n{bad_css}\n/* /defect */" if enabled else good_css


GOOD = {
    "no-focus": "a:focus-visible, button:focus-visible, summary:focus-visible { outline: 3px solid var(--color-primary); outline-offset: 2px; }",
    "small-targets": ".nav__link { display: inline-flex; align-items: center; min-height: 44px; padding-inline: var(--space-2); font-size: var(--text-sm); }",
    "literal-values": ".card { background: var(--color-surface); border: 1px solid var(--color-border); padding: var(--space-5); border-radius: var(--radius-md); }",
    "tiny-text": ".footer__legal { font-size: var(--text-sm); color: var(--color-muted); }",
    "weak-cta": ".btn--primary { background: var(--color-primary); color: var(--color-on-primary); border-color: var(--color-primary); font-weight: 600; }",
}
BAD = {
    "no-focus": "a, button { outline: none; }",
    "small-targets": ".nav__link { display: inline-block; padding: 0 var(--space-1); font-size: var(--text-sm); line-height: 1.2; }",
    "literal-values": ".card { background: #ffffff; border: 1px solid #e5e7eb; padding: 28px; border-radius: 10px; }",
    "tiny-text": ".footer__legal { font-size: 11px; color: var(--color-muted); }",
    "weak-cta": ".btn--primary { background: transparent; color: var(--color-text); border-color: var(--color-border); font-weight: 500; }",
}


def _palette_css(p: dict) -> str:
    return "\n".join(f"  --color-{k.replace('_', '-')}: {v};" for k, v in p.items())


def html_for(brief: DirectionBrief, prefs: dict, intake_d: dict, defects: list[str] | None = None) -> str:
    defects = SEEDED if defects is None else defects
    b = brief
    theme = prefs.get("theme", "light")
    pal = (b.dark_palette or b.palette).model_dump() if theme == "dark" else b.palette.model_dump()
    dark_block = ""
    if theme == "both" and b.dark_palette:
        dark_block = "@media (prefers-color-scheme: dark) {\n  :root {\n" + _palette_css(b.dark_palette.model_dump()) + "\n  }\n}"
    shape = settings.option("shapes", b.shape)
    density = settings.option("density", b.density)
    motion = settings.option("motion", b.motion)
    m = density["space_multiplier"]
    space = {i: round(4 * i * m) for i in (1, 2, 3, 4, 5, 6, 8, 12, 16)}
    name = html_lib.escape(intake_d.get("product_name") or "Acme")
    desc = html_lib.escape(prefs.get("product_description") or "The fastest way to ship reliable software, without the busywork.")
    sections = intake_d.get("sections") or ["hero", "features", "cta", "footer"]
    split = (b.layout_id or "").startswith("split") or "split" in b.layout_archetype.lower()
    fonts_q = "&".join(sorted({f"family={f.replace(' ', '+')}:wght@400;600;700" for f in (b.heading_font, b.body_font)}))

    body = []
    for s in sections:
        if s == "hero":
            body.append(f"""
    <section class="hero{' hero--split' if split else ''}" data-component="hero" aria-labelledby="hero-title">
      <div class="hero__copy">
        <p class="eyebrow">New · {name} 2.0</p>
        <h1 id="hero-title" class="hero__title">Ship with confidence, <span class="hero__accent">every single day</span></h1>
        <p class="hero__lead">{desc}</p>
        <div class="hero__actions">
          <a class="btn btn--primary" href="#get-started">Start free trial</a>
          <a class="btn btn--ghost" href="#demo">Book a demo</a>
        </div>
      </div>
      <div class="hero__visual" role="img" aria-label="Product screenshot placeholder" data-placeholder="hero-image 1200x800, product dashboard screenshot"></div>
    </section>""")
        elif s in ("features", "how-it-works"):
            cards = "".join(f"""
        <article class="card">
          <svg class="card__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12l5 5L20 6" fill="none" stroke="currentColor" stroke-width="2"/></svg>
          <h3 class="card__title">{t}</h3>
          <p class="card__body">{d}</p>
        </article>""" for t, d in [("Instant previews", "Every pull request gets a live preview link your whole team can review."),
                                   ("Guardrails built in", "Policies catch risky changes before they reach production."),
                                   ("Insights that matter", "See deploy frequency and failure rate without building a dashboard.")])
            body.append(f"""
    <section class="features" data-component="{s}" aria-labelledby="{s}-title">
      <h2 id="{s}-title" class="section__title">Everything you need to move fast</h2>
      <div class="features__grid">{cards}
      </div>
    </section>""")
        elif s == "testimonials":
            body.append("""
    <section class="testimonials" data-component="testimonials" aria-labelledby="testimonials-title">
      <h2 id="testimonials-title" class="section__title">Teams ship more, and sleep better</h2>
      <div class="testimonials__grid">
        <figure class="quote"><blockquote>“We cut our release time from a day to twenty minutes.”</blockquote><figcaption>Priya N., Staff Engineer</figcaption></figure>
        <figure class="quote"><blockquote>“The previews alone paid for it in the first week.”</blockquote><figcaption>Marco L., CTO</figcaption></figure>
      </div>
    </section>""")
        elif s in ("cta", "newsletter"):
            body.append(f"""
    <section class="cta" data-component="{s}" aria-labelledby="{s}-title">
      <h2 id="{s}-title" class="section__title">Ready when you are</h2>
      <p class="cta__text">Free for 14 days. No credit card required.</p>
      <a class="btn btn--primary" id="get-started" href="#signup">Get started</a>
    </section>""")
        elif s == "footer":
            continue
        else:
            title = (settings.section(s) or {"name": s.title()})["name"]
            body.append(f"""
    <section class="generic" data-component="{s}" aria-labelledby="{s}-title">
      <h2 id="{s}-title" class="section__title">{html_lib.escape(title)}</h2>
      <div class="features__grid">
        <article class="card"><h3 class="card__title">{html_lib.escape(title)} one</h3><p class="card__body">Realistic content for this block will come from your copy.</p></article>
        <article class="card"><h3 class="card__title">{html_lib.escape(title)} two</h3><p class="card__body">Each item explains one concrete benefit in a sentence.</p></article>
      </div>
    </section>""")

    css = f"""
:root {{
  /* Color roles */
{_palette_css(pal)}
  /* Typography */
  --font-heading: "{b.heading_font}", system-ui, sans-serif;
  --font-body: "{b.body_font}", system-ui, sans-serif;
  --text-sm: 0.875rem; --text-base: 1rem; --text-lg: 1.25rem;
  --text-xl: clamp(1.5rem, 1.2rem + 1vw, 2rem); --text-display: clamp(2.25rem, 1.6rem + 3vw, 4rem);
  /* Spacing (density: {b.density}) */
{chr(10).join(f'  --space-{k}: {v}px;' for k, v in space.items())}
  /* Shape: {b.shape} */
  --radius-sm: {shape['radius_sm']}; --radius-md: {shape['radius_md']}; --radius-lg: {shape['radius_lg']}; --radius-button: {shape['radius_button']};
  --shadow: {shape['shadow']};
  /* Motion: {b.motion} */
  --duration: {motion['duration_base']}; --easing: {motion['easing']};
  /* Breakpoints (documented): 768px, 1024px, 1280px */
}}
{dark_block}
*, *::before, *::after {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: var(--font-body); font-size: var(--text-base); line-height: 1.6; color: var(--color-text); background: var(--color-bg); }}
h1, h2, h3 {{ font-family: var(--font-heading); line-height: 1.15; margin: 0; }}
a {{ color: var(--color-primary); }}
{_defect("no-focus", BAD["no-focus"], "no-focus" in defects, GOOD["no-focus"])}
.site-header {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-4) var(--space-6); border-bottom: 1px solid var(--color-border); }}
.logo {{ font-family: var(--font-heading); font-weight: 700; font-size: var(--text-lg); color: var(--color-text); text-decoration: none; }}
.nav {{ display: flex; gap: var(--space-2); flex-wrap: wrap; }}
{_defect("small-targets", BAD["small-targets"], "small-targets" in defects, GOOD["small-targets"])}
.nav__link {{ color: var(--color-text); text-decoration: none; }}
.nav__link:hover {{ color: var(--color-primary); }}
main {{ display: block; }}
section {{ padding: var(--space-16) var(--space-6); }}
.hero {{ display: grid; gap: var(--space-8); text-align: center; justify-items: center; }}
.hero--split {{ text-align: left; justify-items: start; }}
.eyebrow {{ font-size: var(--text-sm); color: var(--color-muted); margin: 0 0 var(--space-3); }}
.hero__title {{ font-size: var(--text-display); max-width: 18ch; }}
.hero__accent {{ color: var(--color-primary); }}
.hero__lead {{ font-size: var(--text-lg); color: var(--color-muted); max-width: 52ch; margin: var(--space-4) 0 var(--space-6); }}
.hero__actions {{ display: flex; gap: var(--space-3); flex-wrap: wrap; justify-content: inherit; }}
.hero__visual {{ width: 100%; max-width: 960px; aspect-ratio: 16 / 10; border-radius: var(--radius-lg); border: 1px solid var(--color-border);
  background: linear-gradient(135deg, var(--color-surface), var(--color-bg)), var(--color-surface); box-shadow: var(--shadow); }}
.btn {{ display: inline-flex; align-items: center; justify-content: center; min-height: 48px; padding: 0 var(--space-6); border-radius: var(--radius-button);
  border: 2px solid var(--color-border); font-weight: 600; text-decoration: none; transition: transform var(--duration) var(--easing), background var(--duration) var(--easing); }}
.btn--ghost {{ color: var(--color-text); background: transparent; }}
.btn--ghost:hover {{ border-color: var(--color-text); }}
{_defect("weak-cta", BAD["weak-cta"], "weak-cta" in defects, GOOD["weak-cta"])}
.btn--primary:hover {{ transform: translateY(-1px); }}
.section__title {{ font-size: var(--text-xl); text-align: center; margin-bottom: var(--space-8); }}
.features__grid, .testimonials__grid {{ display: grid; gap: var(--space-5); max-width: 1120px; margin: 0 auto; }}
{_defect("literal-values", BAD["literal-values"], "literal-values" in defects, GOOD["literal-values"])}
.card__icon {{ width: 28px; height: 28px; color: var(--color-accent); }}
.card__title {{ font-size: var(--text-lg); margin: var(--space-3) 0 var(--space-2); }}
.card__body {{ color: var(--color-muted); margin: 0; }}
.quote {{ margin: 0; padding: var(--space-6); border-left: 3px solid var(--color-accent); background: var(--color-surface); border-radius: var(--radius-md); }}
.quote blockquote {{ margin: 0 0 var(--space-3); font-size: var(--text-lg); }}
.quote figcaption {{ color: var(--color-muted); font-size: var(--text-sm); }}
.cta {{ text-align: center; background: var(--color-surface); border-block: 1px solid var(--color-border); }}
.cta__text {{ color: var(--color-muted); margin: 0 0 var(--space-6); }}
.site-footer {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-4); padding: var(--space-8) var(--space-6); border-top: 1px solid var(--color-border); }}
{_defect("tiny-text", BAD["tiny-text"], "tiny-text" in defects, GOOD["tiny-text"])}
@media (min-width: 768px) {{
  .features__grid {{ grid-template-columns: repeat(3, 1fr); }}
  .testimonials__grid {{ grid-template-columns: repeat(2, 1fr); }}
  .hero--split {{ grid-template-columns: 1.1fr 1fr; align-items: center; }}
}}
@media (min-width: 1024px) {{ section {{ padding-inline: var(--space-16); }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name} — {html_lib.escape(b.name)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?{fonts_q}&display=swap">
  <style>{css}</style>
</head>
<body>
  <header class="site-header" data-component="site-header">
    <a class="logo" href="#">{name}</a>
    <nav class="nav" aria-label="Main">
      <a class="nav__link" href="#features">Product</a>
      <a class="nav__link" href="#pricing">Pricing</a>
      <a class="nav__link" href="#docs">Docs</a>
    </nav>
  </header>
  <main>{''.join(body)}
  </main>
  <footer class="site-footer" data-component="site-footer">
    <span class="logo">{name}</span>
    <p class="footer__legal">© 2026 {name}, Inc. All rights reserved.</p>
  </footer>
</body>
</html>
"""


# ------------------------------------------------------------------- style lock
def style_character(brief: dict, notes: str) -> StyleCharacter:
    return StyleCharacter(
        character=f"{brief['name']}: {brief['reference_style']} direction, {brief['density']} spacing, {brief['shape']} shapes, "
                  f"{brief['heading_font']} headings over {brief['body_font']} body text.",
        signature_elements=[brief["signature_element"], f"{brief['layout_archetype'][:80]}"],
        must_keep=["the palette roles", "the heading font", "the hero arrangement"] + ([f"user note: {notes}"] if notes else []),
    )


# ----------------------------------------------------------------------- review
def review(html: str, audit: dict, previous: list[dict], change_requests: list[dict]) -> ReviewResult:
    present = set(re.findall(r"/\* defect:([\w-]+) \*/", html))
    issues = []
    for key, (iid, crit, sev, selector, vp, ev, fix, expl) in DEFECTS.items():
        was_raised = any(p["id"] == iid for p in previous)
        if key in present:
            issues.append(Issue(id=iid, criterion=crit, severity=sev, selector=selector, viewport=vp, evidence=ev,
                                suggested_fix=fix, explanation=expl, status="open"))
        elif was_raised:
            issues.append(Issue(id=iid, criterion=crit, severity=sev, selector=selector, viewport=vp, evidence=ev,
                                suggested_fix=fix, explanation=expl, status="resolved"))
    for cr in change_requests:
        done = f"/* change:{cr['id']} */" in html
        issues.append(Issue(**{**cr, "status": "resolved" if done else "open"}))
    open_by_crit: dict[str, int] = {}
    for i in issues:
        if i.status == "open":
            open_by_crit[i.criterion] = open_by_crit.get(i.criterion, 0) + (2 if i.severity == "high" else 1)
    base = {"B1": 4, "B2": 4, "B3": 4, "B4": 5, "B5": 4, "B6": 4, "B7": 4, "B8": 5, "B9": 5}
    scores = [CriterionScore(criterion=c, score=max(2, min(5, s - open_by_crit.get(c, 0) + (1 if not open_by_crit and c in ("B2", "B3") else 0))),
                             evidence="Open issues: " + ", ".join(i.id for i in issues if i.criterion == c and i.status == "open")
                             if open_by_crit.get(c) else "No open issues for this criterion (mock reviewer).")
              for c, s in base.items()]
    n_open = sum(1 for i in issues if i.status == "open")
    return ReviewResult(summary=f"Mock review: {n_open} open issue(s); audit {'passed' if audit.get('passed') else 'failed'}.",
                        scores=scores, issues=issues)


# ---------------------------------------------------------------------- execute
def execute(editor, html: str, top_issues: list[dict]) -> str:
    by_issue = {v[0]: k for k, v in DEFECTS.items()}
    fixed = []
    for iss in top_issues:
        key = by_issue.get(iss["id"])
        if key:
            m = re.search(rf"/\* defect:{key} \*/\n.*?\n/\* /defect \*/", editor.target.read_text(), flags=re.S)
            if m:
                ok, _ = editor.handle({"command": "str_replace", "path": "index.html", "old_str": m.group(0), "new_str": GOOD[key]})
                if ok:
                    fixed.append(iss["id"])
        elif iss["id"].startswith("chg_"):
            ok, _ = editor.handle({"command": "str_replace", "path": "index.html", "old_str": "</style>",
                                   "new_str": f"/* change:{iss['id']} */\n</style>"})
            if ok:
                fixed.append(iss["id"])
    return "Mock executor fixed: " + (", ".join(fixed) or "nothing")


# ---------------------------------------------------------------------- handoff
def handoff(components: list[str], tokens: dict, spec: dict, review_d: dict | None) -> str:
    rows = "\n".join(f"| `{k}` | `{v}` |" for k, v in list(tokens.items())[:60])
    comps = "\n".join(f"### `{c}`\n- Purpose: see the screenshots.\n- States: hover, focus-visible, active.\n- Responsive: stacks below 768px.\n" for c in components)
    return f"""# HANDOFF — {spec.get('direction_id', '')}

> Generated in mock mode. Run with an API key for a full written spec.

## Design character
{spec.get('character', '')}

## How to build from this
1. Set up the tokens below as your theme (CSS variables, or your framework's theme config).
2. Build components top-down in the order they appear.
3. Compare against `screenshots/` at 375, 768 and 1440px.

## Component inventory
{comps}
## Tokens
| Token | Value |
|---|---|
{rows}

## Placeholders
Elements with `data-placeholder` describe the image to supply.

## Accessibility notes
Focus states use `:focus-visible`; tap targets are at least 44px on mobile.

## Known limitations
Mock-mode content is generic.
"""
