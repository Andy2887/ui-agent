"use client";
// Live combined preview (§5.3): a mini page driven only by CSS custom properties — no LLM, no lag.
import { type CSSProperties, type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { previewVars } from "@/lib/logic";
import type { LayoutPreset, Palette, Preferences, Presets, StylePreset } from "@/lib/types";

export function LivePreview({ prefs, presets, palette, style, layout }: {
  prefs: Preferences; presets: Presets; palette: Palette; style: StylePreset | null; layout: LayoutPreset | null;
}) {
  const vars = previewVars(prefs, presets, palette, style) as CSSProperties;
  const name = prefs.product_name || "Northwind";
  const arrangement = layout?.shell === "sidebar" || layout?.shell === "split-list" ? "app"
    : layout?.id === "split-hero" || layout?.id === "bento" || layout?.hero?.[0]?.cols.length === 2 ? "split" : "center";
  const cards = ["Previews", "Guardrails", "Insights"];

  if (arrangement === "app") {
    return (
      <div className="lp lp--app" style={vars}>
        <aside className="lp__side"><b>{name}</b><span className="is-active">Overview</span><span>Deploys</span><span>Settings</span></aside>
        <div className="lp__main">
          <div className="lp__h">Overview</div>
          <div className="lp__kpis">{["Deploys", "Uptime", "Lead time"].map((k, i) => (
            <div key={k} className="lp__card"><small>{k}</small><strong>{["128", "99.9%", "42m"][i]}</strong></div>))}</div>
          <div className="lp__card lp__chart">{[40, 65, 50, 80, 70, 95, 60].map((h, i) => <span key={i} style={{ height: `${h}%` }} />)}</div>
          <div className="lp__actions"><span className="lp__btn">New deploy</span></div>
        </div>
      </div>
    );
  }
  return (
    <div className="lp" style={vars}>
      <div className="lp__nav"><b>{name}</b><span>Product</span><span>Pricing</span><span className="lp__btn lp__btn--sm">Sign up</span></div>
      <div className={`lp__hero lp__hero--${arrangement}`}>
        <div>
          <div className="lp__h">{prefs.product_description ? prefs.product_description.slice(0, 48) : "Ship confidently, every day"}</div>
          <p>Previews, guardrails and rollbacks in one place.</p>
          <div className="lp__actions"><span className="lp__btn">Start free</span><span className="lp__btn lp__btn--ghost">Demo</span></div>
        </div>
        {arrangement === "split" && <div className="lp__visual" />}
      </div>
      <div className="lp__cards">{cards.map((c) => (
        <div key={c} className="lp__card"><i /><strong>{c}</strong><small>One clear sentence about it.</small></div>))}</div>
      <div className="lp__cta"><strong>Ready when you are</strong><span className="lp__btn">Get started</span></div>
    </div>
  );
}

/** Scales its content down (never up) so it fits the height it is given, instead of scrolling. */
export function FitBox({ children }: { children: ReactNode }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const o = outer.current, i = inner.current;
    if (!o || !i) return;
    const update = () => setScale(i.offsetHeight ? Math.min(1, o.clientHeight / i.offsetHeight) : 1);
    const ro = new ResizeObserver(update);
    ro.observe(o);
    ro.observe(i);
    update();
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={outer} className="fit">
      <div ref={inner} className="fit__inner" style={{ transform: `scale(${scale})` }}>{children}</div>
    </div>
  );
}
