"""Playwright session: render at each viewport, viewport-height tiles, DOM summary,
and the raw facts the Layer-A checks need (plan §4.8 `render`)."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser as PWBrowser
from playwright.async_api import async_playwright

from .. import settings

AXE_JS = (Path(__file__).parent / "vendor" / "axe.min.js").read_text()

FACTS_JS = r"""
(vpName) => {
  const vw = document.documentElement.clientWidth;
  const sw = document.documentElement.scrollWidth;
  const visible = (el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.01;
  };
  const sel = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else if (el.classList.length) s += '.' + [...el.classList].slice(0, 2).join('.');
    const comp = el.closest('[data-component]');
    return comp && comp !== el ? `[data-component=${comp.dataset.component}] ${s}` : s;
  };

  const overflow = [];
  if (sw > vw + 1) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > vw + 1) {
        overflow.push({ selector: sel(el), right: Math.round(r.right) });
        if (overflow.length >= 8) break;
      }
    }
  }

  const interactive = [...document.querySelectorAll(
    'a[href], button, input:not([type=hidden]), select, textarea, [role=button], summary')].filter(visible);
  const targets = [];
  for (const el of interactive) {
    const inlineLink = el.tagName === 'A' && el.closest('p') && getComputedStyle(el).display === 'inline';
    if (inlineLink) continue; // WCAG 2.5.8 exempts links inside sentences
    const r = el.getBoundingClientRect();
    if (r.width < 44 || r.height < 44)
      targets.push({ selector: sel(el), w: Math.round(r.width), h: Math.round(r.height),
                     text: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40) });
  }

  const tiny = []; const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode; const el = t.parentElement;
    if (!t.textContent.trim() || !el || seen.has(el)) continue;
    seen.add(el);
    if (!visible(el) || el.closest('[aria-hidden=true]')) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 12) tiny.push({ selector: sel(el), size: fs, text: t.textContent.trim().slice(0, 40) });
  }
  const bodyFont = parseFloat(getComputedStyle(document.body).fontSize);
  // Body copy = paragraphs/list items with sentence-length text (short labels may be smaller).
  const smallBody = [...document.querySelectorAll('main p, main li')].filter(visible)
    .filter((el) => (el.innerText || '').trim().length > 60)
    .map((el) => ({ selector: sel(el), size: parseFloat(getComputedStyle(el).fontSize) }))
    .filter((x) => x.size < 16);

  // Playwright's full-page screenshot leaves an empty style="" on inputs; only count real declarations.
  const inlineStyles = [...document.querySelectorAll('[style]')].filter((el) => el.getAttribute('style').trim()).map(sel);
  const topLevel = [...document.querySelectorAll('body > header, body > nav, body > footer, body > section, body > aside, main > *, body > div > header, body > div > main > *, body > div > footer')]
    .filter((el) => !['SCRIPT', 'STYLE', 'TEMPLATE'].includes(el.tagName));
  const missingComponent = topLevel.filter((el) => !el.hasAttribute('data-component')).map(sel);

  // A9 layout balance. A column "has content" where it shows text, media, controls or a visible
  // panel; grid/flex stretching alone adds nothing, so a short column beside a tall one shows up.
  const clear = (c) => !c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)';
  const bgOf = (el) => { for (; el; el = el.parentElement) { const c = getComputedStyle(el).backgroundColor;
    if (!clear(c)) return c; } return 'rgb(255, 255, 255)'; };
  const MEDIA = new Set(['IMG', 'SVG', 'VIDEO', 'CANVAS', 'IFRAME', 'INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'HR', 'PICTURE']);
  const contentBox = (root, skipSelf) => {
    let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
    const add = (r) => { if (r.width < 1 || r.height < 1 || r.width > vw * 0.9) return;
      top = Math.min(top, r.top + scrollY); bottom = Math.max(bottom, r.bottom + scrollY);
      left = Math.min(left, r.left); right = Math.max(right, r.right); };
    const walk = (el) => {
      if (!visible(el)) return;
      const s = getComputedStyle(el); const r = el.getBoundingClientRect();
      if (!(skipSelf && el === root)) {
        if (MEDIA.has(el.tagName.toUpperCase()) || el.hasAttribute('data-placeholder') || el.getAttribute('role') === 'img') { add(r); return; }
        if (s.backgroundImage !== 'none' || (!clear(s.backgroundColor) && s.backgroundColor !== bgOf(el.parentElement))) add(r);
        const sides = ['Top', 'Right', 'Bottom', 'Left'].filter((d) => parseFloat(s[`border${d}Width`]) > 0 && s[`border${d}Style`] !== 'none');
        if (sides.length === 4) add(r);
        else for (const d of sides) { const w = parseFloat(s[`border${d}Width`]);
          add(d === 'Top' ? new DOMRect(r.left, r.top, r.width, w) : d === 'Bottom' ? new DOMRect(r.left, r.bottom - w, r.width, w)
            : d === 'Left' ? new DOMRect(r.left, r.top, w, r.height) : new DOMRect(r.right - w, r.top, w, r.height)); }
      }
      for (const n of el.childNodes) {
        if (n.nodeType === 3 && n.textContent.trim()) { const rg = document.createRange(); rg.selectNodeContents(n); add(rg.getBoundingClientRect()); }
        else if (n.nodeType === 1) walk(n);
      }
    };
    walk(root);
    return top === Infinity ? null : { top, bottom, left, right };
  };
  const hasSticky = (el) => getComputedStyle(el).position === 'sticky' || [...el.querySelectorAll('*')].some((d) => getComputedStyle(d).position === 'sticky');
  const minBand = Math.max(160, vw * 0.17);
  const lopsided = [];
  for (const box of document.querySelectorAll('body *')) {
    const s = getComputedStyle(box);
    const isRow = s.display.endsWith('grid') || (s.display.endsWith('flex') && s.flexDirection.startsWith('row'));
    if (!isRow || !visible(box)) continue;
    const kids = [...box.children].filter((k) => visible(k) && !['absolute', 'fixed'].includes(getComputedStyle(k).position)
      && k.getBoundingClientRect().width >= 160);
    // Group children into visual rows by vertical overlap.
    const rows = [];
    for (const k of kids.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)) {
      const r = k.getBoundingClientRect();
      const row = rows.find((g) => Math.min(g.bottom, r.bottom) - Math.max(g.top, r.top) > 0.5 * Math.min(g.bottom - g.top, r.height));
      if (row) { row.kids.push(k); row.top = Math.min(row.top, r.top); row.bottom = Math.max(row.bottom, r.bottom); }
      else rows.push({ kids: [k], top: r.top, bottom: r.bottom });
    }
    for (const row of rows) {
      if (row.kids.length < 2) continue;
      const cols = row.kids.map((k) => ({ k, c: contentBox(k, false) })).filter((x) => x.c);
      if (cols.length < 2) continue;
      const top = Math.min(...cols.map((x) => x.c.top)); const bottom = Math.max(...cols.map((x) => x.c.bottom));
      if (bottom - top < 300) continue;
      for (const { k, c } of cols) {
        const above = c.top - top, below = bottom - c.bottom, band = Math.max(above, below);
        const fill = (c.bottom - c.top) / (bottom - top);
        // Sticky only rescues a row the visitor scrolls through; in a row shorter than the screen it changes nothing.
        if (band < minBand || fill > 0.6 || (hasSticky(k) && bottom - top > innerHeight)) continue;
        const r = k.getBoundingClientRect();
        lopsided.push({ kind: 'short-column', row: sel(box), column: sel(k), empty_px: Math.round(band),
          empty_where: above > below ? 'above' : 'below', fill: Math.round(fill * 100) / 100, row_height: Math.round(bottom - top),
          column_side: r.left + r.width / 2 < vw / 2 ? 'left' : 'right', y: Math.round(top) });
      }
    }
    if (lopsided.length >= 12) break;
  }
  // Whole blocks pushed right with an empty left (left-aligned text with space on its right is normal reading layout).
  const blocks = [...document.querySelectorAll('[data-component]')].filter((el) => visible(el) && !el.parentElement.closest('[data-component]'))
    .map((el) => ({ el, c: contentBox(el, true) })).filter((x) => x.c && x.el.getBoundingClientRect().height >= 150);
  const lefts = blocks.map((x) => x.c.left).sort((a, b) => a - b);
  const pageLeft = lefts.length ? lefts[Math.floor(lefts.length / 2)] : 0;
  const offside = blocks.filter(({ c }) => c.left - pageLeft >= Math.max(200, vw * 0.2) && Math.abs((c.left + c.right) / 2 - vw / 2) > vw * 0.08)
    .map(({ el, c }) => ({ kind: 'pushed-right', component: el.dataset.component, empty_left_px: Math.round(c.left - pageLeft),
                           content_left: Math.round(c.left), page_left: Math.round(pageLeft), y: Math.round(c.top) }));

  const components = [...document.querySelectorAll('[data-component]')].map((el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    const h = el.querySelector('h1, h2, h3');
    const btn = el.querySelector('a.btn, button, .btn, [class*=button]');
    return {
      name: el.dataset.component,
      box: [Math.round(r.x), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)],
      bg: s.backgroundColor,
      heading: h ? { tag: h.tagName.toLowerCase(), text: h.innerText.trim().slice(0, 90),
                     size: getComputedStyle(h).fontSize, weight: getComputedStyle(h).fontWeight,
                     font: getComputedStyle(h).fontFamily.split(',')[0] } : null,
      primary_button: btn ? { text: (btn.innerText || '').trim().slice(0, 40),
                              bg: getComputedStyle(btn).backgroundColor, color: getComputedStyle(btn).color,
                              radius: getComputedStyle(btn).borderRadius,
                              above_fold: btn.getBoundingClientRect().top + scrollY < innerHeight } : null,
    };
  });
  return {
    viewport: vpName, client_width: vw, scroll_width: sw,
    page_height: document.documentElement.scrollHeight,
    overflow, small_targets: targets, interactive_count: interactive.length,
    tiny_text: tiny.slice(0, 15), body_font_px: bodyFont, small_body_text: smallBody.slice(0, 10),
    inline_styles: inlineStyles.slice(0, 10), inline_style_count: inlineStyles.length,
    missing_component: missingComponent.slice(0, 10),
    components, balance: [...lopsided, ...offside].slice(0, 12),
    h1_count: document.querySelectorAll('h1').length,
    headings: [...document.querySelectorAll('h1,h2,h3,h4')].slice(0, 40).map((h) => h.tagName.toLowerCase() + ': ' + h.innerText.trim().slice(0, 60)),
    body_font_family: getComputedStyle(document.body).fontFamily,
    root_custom_properties: [...document.styleSheets].flatMap((ss) => { try { return [...ss.cssRules]; } catch { return []; } })
      .filter((r) => r.selectorText === ':root').flatMap((r) => [...r.style]).filter((p) => p.startsWith('--')).length,
  };
}
"""

FOCUS_JS = r"""
(i) => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  if (el.dataset.uiaFocus) return { wrapped: true };
  el.dataset.uiaFocus = String(i);
  const snap = () => { const s = getComputedStyle(el);
    const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 ? `${s.outlineStyle} ${s.outlineWidth} ${s.outlineColor}` : 'none';
    return [outline, s.boxShadow, s.backgroundColor, s.borderColor, s.color, s.textDecorationLine].join(' | '); };
  // Finish focus-ring transitions first: the base layer's reduced-motion rule keeps them at 0.01ms, and a
  // snapshot taken at a transition's start would read the previous state.
  const settle = () => document.getAnimations().forEach((a) => { try { a.finish(); } catch (e) {} });  // infinite ones throw
  settle(); const focused = snap(); el.blur(); settle(); const unfocused = snap(); el.focus(); settle();
  let selector = el.tagName.toLowerCase() + (el.classList.length ? '.' + [...el.classList].slice(0, 2).join('.') : '');
  const comp = el.closest('[data-component]');
  if (comp) selector = `[data-component=${comp.dataset.component}] ${selector}`;
  return { selector, text: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40), visible: focused !== unfocused };
}
"""

# A5 autofix support: for each sentence-length <p>/<li> in <main> under 16px, find the CSS rule that sets its
# size. A rule counts when raising its font-size to max(1rem, value) lifts the element to 16px or more; candidates
# are rules that set font-size and match the element or an ancestor, latest first. Every probe is reverted.
FONT_FLOOR_JS = r"""
() => {
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const rules = [];
  const walk = (list) => { for (const r of list) { if (r instanceof CSSStyleRule) rules.push(r); if (r.cssRules) walk(r.cssRules); } };
  for (const ss of document.styleSheets) { try { walk(ss.cssRules); } catch (e) {} }
  const matches = (el, sel) => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    try { if (n.matches(sel)) return true; } catch (e) { return false; } } return false; };
  // Under emulated reduced motion, short transitions still run; read the end value, not the start.
  const settle = () => document.getAnimations().forEach((a) => { try { a.finish(); } catch (e) {} });  // infinite ones throw
  const size = (el) => { settle(); return parseFloat(getComputedStyle(el).fontSize); };
  const found = [];
  const small = [...document.querySelectorAll('main p, main li')].filter(visible)
    .filter((el) => (el.innerText || '').trim().length > 60 && size(el) < 16);
  for (const el of small) {
    const before = size(el);
    for (const r of [...rules].reverse()) {
      const value = r.style.getPropertyValue('font-size');
      if (!value || !matches(el, r.selectorText)) continue;
      const prio = r.style.getPropertyPriority('font-size');
      r.style.setProperty('font-size', `max(1rem, ${value})`, prio);
      const after = size(el);
      r.style.setProperty('font-size', value, prio);
      settle();
      if (after !== before) {
        if (after >= 15.99 && !found.some((f) => f.selector === r.selectorText && f.value === value))
          found.push({ selector: r.selectorText, value, before, after });
        break;
      }
    }
  }
  return found;
}
"""

AXE_RUN_JS = """
async () => {
  const r = await axe.run(document, { resultTypes: ['violations'] });
  return r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help,
    nodes: v.nodes.slice(0, 6).map(n => ({ target: n.target.join(' '), summary: (n.failureSummary || '').slice(0, 300) })) }));
}
"""

NO_MOTION_CSS = "*,*::before,*::after{transition:none!important;animation:none!important;}"


class BrowserSession:
    """One Chromium per process; pages are cheap."""

    def __init__(self) -> None:
        self._pw = None
        self._browser: PWBrowser | None = None
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(4)

    async def browser(self) -> PWBrowser:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch()
        return self._browser

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None
        # Asyncio primitives bind to the loop that first waits on them; start fresh for the next loop.
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(4)

    async def render(self, html_path: Path, out_dir: Path, *, tiles: bool = True, deep_checks: bool = True) -> dict:
        """Render one HTML file at every viewport. Returns paths (relative to out_dir's run root
        are computed by the caller) plus the raw facts for the audit."""
        cfg = settings.config()
        out_dir.mkdir(parents=True, exist_ok=True)
        allowed = set(cfg["allowed_hosts"])
        result: dict = {"screenshots": {}, "tiles": {}, "facts": {}, "axe": [], "focus": [],
                        "console_errors": [], "blocked_requests": [], "font_floor_rules": []}
        async with self._sem:
            browser = await self.browser()
            for vp, (w, h) in cfg["viewports"].items():
                ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                                reduced_motion="reduce")
                page = await ctx.new_page()

                def on_request(req, _vp=vp):
                    u = urlparse(req.url)
                    if u.scheme in ("file", "data", "about", "blob"):
                        return
                    if u.hostname not in allowed and req.url not in result["blocked_requests"]:
                        result["blocked_requests"].append(req.url)

                def on_console(msg):
                    if msg.type != "error":
                        return
                    loc = (msg.location or {}).get("url", "")
                    host = urlparse(loc).hostname
                    if "Failed to load resource" in msg.text and (host in allowed or not loc):
                        return  # offline font hosts are environmental, not design defects
                    if msg.text not in result["console_errors"]:
                        result["console_errors"].append(msg.text[:300])

                page.on("request", on_request)
                page.on("console", on_console)
                page.on("pageerror", lambda exc: result["console_errors"].append(f"pageerror: {exc}"[:300]))
                try:
                    await page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=20000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=4000)
                    except Exception:
                        pass
                    await page.evaluate("document.fonts && document.fonts.ready")
                    await page.wait_for_timeout(150)

                    full = out_dir / f"{vp}.png"
                    await page.screenshot(path=str(full), full_page=True)
                    result["screenshots"][vp] = full
                    facts = await page.evaluate(FACTS_JS, vp)
                    result["facts"][vp] = facts

                    if tiles:
                        n = min(math.ceil(facts["page_height"] / h), cfg["max_tiles"][vp])
                        paths = []
                        for i in range(n):
                            tile_h = min(h, facts["page_height"] - i * h)
                            if tile_h <= 0:
                                break
                            p = out_dir / f"{vp}-tile{i + 1}.png"
                            await page.screenshot(path=str(p), full_page=True,
                                                  clip={"x": 0, "y": i * h, "width": w, "height": tile_h})
                            paths.append(p)
                        result["tiles"][vp] = paths

                    if deep_checks and vp == "mobile" and facts["small_body_text"]:
                        result["font_floor_rules"] = await page.evaluate(FONT_FLOOR_JS)
                    if deep_checks and vp in ("desktop", "mobile"):
                        await page.add_script_tag(content=AXE_JS)
                        for v in await page.evaluate(AXE_RUN_JS):
                            if not any(x["id"] == v["id"] for x in result["axe"]):
                                v["viewport"] = vp
                                result["axe"].append(v)
                    if deep_checks and vp == "desktop":
                        await page.add_style_tag(content=NO_MOTION_CSS)
                        await page.evaluate("window.scrollTo(0,0); document.activeElement && document.activeElement.blur()")
                        for i in range(min(facts["interactive_count"] + 2, 40)):
                            await page.keyboard.press("Tab")
                            r = await page.evaluate(FOCUS_JS, i)
                            if r is None:
                                continue
                            if r.get("wrapped"):
                                break
                            result["focus"].append(r)
                finally:
                    await ctx.close()
        return result

    async def pdf(self, html_path: Path, out_path: Path, width: int = 1440) -> None:
        browser = await self.browser()
        ctx = await browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
        page = await ctx.new_page()
        try:
            await page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=20000)
            await page.add_style_tag(content="@media print { [data-component] { break-inside: avoid; } }")
            await page.emulate_media(media="screen")
            await page.pdf(path=str(out_path), width=f"{width}px", print_background=True)
        finally:
            await ctx.close()


_session: BrowserSession | None = None


def get_browser() -> BrowserSession:
    global _session
    if _session is None:
        _session = BrowserSession()
    return _session
