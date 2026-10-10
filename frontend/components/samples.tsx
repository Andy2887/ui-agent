"use client";
// Live samples rendered from the preset files (§5.2): every option is *shown*, not named.
import type { CSSProperties, ReactNode } from "react";
import { PAIRS, contrast, paletteFromBrand, scale } from "@/lib/color";
import type { ColorDirection, Palette, SimpleOption, StylePreset, TypographyPreset, WireRow } from "@/lib/types";

const v = (vars: Record<string, string | number>) => vars as CSSProperties;

/* ---------------------------------------------------------------- style / mood */

function Deco({ kind, accent, primary }: { kind: string; accent: string; primary: string }) {
  switch (kind) {
    case "glow": return <div className="deco deco--glow" style={v({ "--a": accent, "--b": primary })} />;
    case "blob": return <div className="deco deco--blob" style={v({ "--a": accent })} />;
    case "block": return <div className="deco deco--block" style={v({ "--a": accent })} />;
    case "rule": return <div className="deco deco--rule" style={v({ "--a": accent })}>№ 01</div>;
    case "frame": return <div className="deco deco--frame" style={v({ "--a": accent })} />;
    case "terminal": return <div className="deco deco--terminal" style={v({ "--a": primary })}>$ deploy --prod<br />✓ live in 42s</div>;
    case "bars": return <div className="deco deco--bars" style={v({ "--a": primary, "--b": accent })}><i /><i /><i /><i /></div>;
    default: return <div className="deco deco--line" style={v({ "--a": accent })} />;
  }
}

export function StyleSample({ style, name }: { style: StylePreset; name?: string }) {
  const s = style.sample;
  return (
    <div className="mini-hero" style={v({ background: s.bg, color: s.text })}>
      <div className="mini-hero__copy">
        <div className="mini-hero__title"
          style={{ fontFamily: `"${s.headingFont}", system-ui`, fontWeight: s.headingWeight, textTransform: s.uppercase ? "uppercase" : "none" }}>
          {name || "Ship faster"}
        </div>
        <div className="mini-hero__text" style={{ fontFamily: `"${s.bodyFont}", system-ui`, color: s.muted }}>
          Deploy previews for every change.
        </div>
        <span className="mini-hero__btn" style={{ background: s.primary, color: s.onPrimary, borderRadius: s.radius, border: s.border, boxShadow: s.shadow, fontFamily: `"${s.bodyFont}", system-ui` }}>
          Get started
        </span>
      </div>
      <Deco kind={s.deco} accent={s.accent} primary={s.primary} />
    </div>
  );
}

/* --------------------------------------------------------------------- layouts */

function Block({ k }: { k: string }) {
  switch (k) {
    case "nav": return <div className="wf wf--nav"><b /><span><i /><i /><i /></span></div>;
    case "copy": case "copy-center":
      return <div className={`wf wf--copy ${k === "copy-center" ? "wf--center" : ""}`}><b /><b className="short" /><i /><i className="short" /><em /></div>;
    case "title": return <div className="wf wf--copy wf--center"><b className="short" /></div>;
    case "media": return <div className="wf wf--media" />;
    case "empty": return <div />;
    case "logos": return <div className="wf wf--logos"><i /><i /><i /><i /><i /></div>;
    case "stat": return <div className="wf wf--card wf--stat"><b /><i /></div>;
    case "chart": return <div className="wf wf--card wf--chart"><span /><span /><span /><span /><span /><span /></div>;
    case "table": case "list": case "faq": case "prose":
      return <div className={`wf wf--lines wf--${k}`}>{Array.from({ length: k === "prose" ? 9 : 5 }, (_, i) => <i key={i} />)}</div>;
    case "form": return <div className="wf wf--card wf--form"><b className="short" /><i /><i /><em /></div>;
    case "cta": return <div className="wf wf--cta"><b className="short" /><em /></div>;
    case "footer": return <div className="wf wf--footer"><i /><i /><i /></div>;
    case "pagehead": return <div className="wf wf--pagehead"><b className="short" /><em /></div>;
    case "filters": return <div className="wf wf--filters"><i /><i /><i /></div>;
    default: return <div className="wf wf--card"><b className="short" /><i /><i className="short" /></div>;
  }
}

function Rows({ rows, unit }: { rows: WireRow[]; unit: number }) {
  return (
    <>
      {rows.map((r, i) => (
        <div key={i} className="wf-row" style={{ height: r.h * unit }}>
          {r.cols.map((c, j) => (
            <div key={j} style={{ gridColumn: `${(c.offset ?? 0) + 1} / span ${c.span}` }}><Block k={c.k} /></div>
          ))}
        </div>
      ))}
    </>
  );
}

export function Wireframe({ rows, shell = "page", unit = 4, maxHeight }: { rows: WireRow[]; shell?: string; unit?: number; maxHeight?: number }) {
  const body = <Rows rows={rows} unit={unit} />;
  return (
    <div className="wireframe" style={{ maxHeight }} aria-hidden="true">
      {shell === "sidebar" && <div className="wf-shell"><div className="wf wf--side"><b /><i /><i /><i /><i /></div><div>{body}</div></div>}
      {shell === "split-list" && <div className="wf-shell wf-shell--split"><div className="wf wf--lines">{Array.from({ length: 8 }, (_, i) => <i key={i} />)}</div><div>{body}</div></div>}
      {shell === "page" && body}
    </div>
  );
}

/* ----------------------------------------------------------------------- color */

export function MiniCard({ p, heading = "Weekly report", headingFont, bodyFont, radius = "10px" }:
  { p: Palette; heading?: string; headingFont?: string; bodyFont?: string; radius?: string }) {
  return (
    <div className="mini-card" style={{ background: p.surface, color: p.text, borderColor: p.border, borderRadius: radius, fontFamily: bodyFont }}>
      <div className="mini-card__row">
        <strong style={{ fontFamily: headingFont }}>{heading}</strong>
        <span className="mini-card__badge" style={{ background: p.accent, color: contrast(p.accent, "#FFFFFF") > contrast(p.accent, "#111111") ? "#FFFFFF" : "#111111" }}>New</span>
      </div>
      <p style={{ color: p.muted }}>3 deploys, 0 incidents.</p>
      <div className="mini-card__input" style={{ borderColor: p.border, background: p.bg, color: p.muted }}>you@team.dev</div>
      <div className="mini-card__row">
        <span className="mini-card__btn" style={{ background: p.primary, color: p.on_primary }}>Save</span>
        <span className="mini-card__btn mini-card__btn--ghost" style={{ color: p.text, borderColor: p.border }}>Cancel</span>
      </div>
    </div>
  );
}

export function ColorSample({ dir, theme }: { dir: ColorDirection; theme: "light" | "dark" | "both" }) {
  const t = theme === "dark" ? "dark" : "light";
  return (
    <div className="color-sample">
      <div className="swatches">{dir.swatches.map((s) => <span key={s} style={{ background: s }} title={s} />)}</div>
      <div className="color-sample__cards">
        {dir.examples.slice(0, 2).map((ex, i) => (
          <div key={i} className="color-sample__bg" style={{ background: ex[t].bg }}><MiniCard p={ex[t]} heading={["Plan", "Report"][i]} /></div>
        ))}
      </div>
      <p className="caption">The agent picks the exact combination.</p>
    </div>
  );
}

export function BrandPalette({ hex, theme }: { hex: string; theme: "light" | "dark" | "both" }) {
  const t = theme === "dark" ? "dark" : "light";
  const { palette, adjustments } = paletteFromBrand(hex, t);
  return (
    <div className="brand-palette">
      <div className="swatches swatches--scale">{scale(hex).map((s, i) => <span key={i} style={{ background: s }} title={s} />)}</div>
      <div className="brand-palette__grid">
        <div className="color-sample__bg" style={{ background: palette.bg }}><MiniCard p={palette} heading="Your brand" /></div>
        <ul className="contrast-list">
          {PAIRS.map(([fg, bg, req, label]) => {
            const r = contrast(palette[fg], palette[bg]);
            const ok = r >= req;
            return (
              <li key={label}>
                <span className="pair" style={{ background: palette[bg], color: palette[fg] }}>Aa</span>
                <span>{label}</span>
                <span className={`badge ${ok ? "badge--ok" : "badge--bad"}`}>{ok ? "AA ✓" : "AA ✗"} {r.toFixed(1)}:1</span>
              </li>
            );
          })}
        </ul>
      </div>
      {adjustments.length > 0 && (
        <p className="note">
          Adjusted for readability: {adjustments.map((a) => `${a.role} ${a.from} → ${a.to} (${a.reason})`).join("; ")}. Same hue, just darker or lighter.
        </p>
      )}
    </div>
  );
}

export function ThemeSample({ theme, light, dark }: { theme: string; light: Palette; dark: Palette }) {
  if (theme === "both") return (
    <div className="theme-sample theme-sample--both">
      <div style={{ background: light.bg }}><MiniCard p={light} heading="Light" /></div>
      <div style={{ background: dark.bg }}><MiniCard p={dark} heading="Dark" /></div>
    </div>
  );
  const p = theme === "dark" ? dark : light;
  return <div className="theme-sample" style={{ background: p.bg }}><MiniCard p={p} heading={theme === "dark" ? "Dark" : "Light"} /></div>;
}

/* ------------------------------------------------------------------ typography */

export function TypographySample({ t, productName }: { t: TypographyPreset; productName?: string | null }) {
  return (
    <div className="type-sample">
      <div className="type-sample__h" style={{ fontFamily: `"${t.heading.family}", ${t.heading.fallback}`, fontWeight: t.heading.weights.at(-1), letterSpacing: t.heading.letter_spacing }}>
        {productName || "Northwind"} makes releases boring
      </div>
      <p style={{ fontFamily: `"${t.body.family}", ${t.body.fallback}` }}>
        Ship every day with previews, guardrails and rollbacks your team trusts.
      </p>
      <div className="type-sample__row" style={{ fontFamily: `"${t.body.family}", ${t.body.fallback}` }}>
        <span className="type-sample__btn">Start free</span>
        <span className="type-sample__num">1,284 · 99.98%</span>
      </div>
    </div>
  );
}

/* -------------------------------------------------------- density / shape / etc. */

export function DensitySample({ opt }: { opt: SimpleOption }) {
  const m = (opt.space_multiplier as number) ?? 1;
  return (
    <div className="density-sample" style={v({ "--s": `${8 * m}px` })}>
      <div className="density-sample__card"><b /><i /><i /></div>
      <ul>{[0, 1, 2].map((i) => <li key={i}><span /><i /></li>)}</ul>
    </div>
  );
}

export function ShapeSample({ opt }: { opt: SimpleOption }) {
  return (
    <div className="shape-sample">
      <span className="shape-sample__btn" style={{ borderRadius: opt.radius_button as string, boxShadow: opt.shadow as string }}>Button</span>
      <span className="shape-sample__input" style={{ borderRadius: opt.radius_sm as string }}>Input</span>
      <span className="shape-sample__card" style={{ borderRadius: opt.radius_md as string, boxShadow: opt.shadow as string }} />
    </div>
  );
}

export function MotionSample({ opt }: { opt: SimpleOption }) {
  return (
    <div className={`motion-sample motion-sample--${opt.id}`} style={v({ "--d": opt.duration_base as string, "--e": opt.easing as string })}>
      <span className="motion-sample__card" /><span className="motion-sample__card" /><span className="motion-sample__card" />
      <span className="motion-sample__btn">Hover</span>
    </div>
  );
}

export function ImagerySample({ opt }: { opt: SimpleOption }) {
  const visual: Record<string, ReactNode> = {
    illustrations: (
      <svg viewBox="0 0 80 50" aria-hidden="true"><circle cx="22" cy="20" r="10" fill="#FBBF24" /><path d="M5 45 Q25 22 40 38 T75 30 V50 H5Z" fill="#34D399" /><rect x="48" y="12" width="20" height="16" rx="3" fill="#60A5FA" /></svg>
    ),
    photos: <div className="imagery-photo"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18l5-6 4 4 3-3 4 5H4z" fill="currentColor" /><circle cx="8" cy="8" r="2" fill="currentColor" /></svg><span>1200×800</span></div>,
    abstract: <div className="imagery-abstract" />,
    none: <div className="imagery-none">Aa</div>,
  };
  return <div className="imagery-sample"><div className="imagery-sample__text"><b /><i /><i /></div><div className="imagery-sample__visual">{visual[opt.id]}</div></div>;
}
