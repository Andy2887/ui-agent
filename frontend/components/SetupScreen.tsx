"use client";
// Screen 1 — Setup (§5): prompt, content inputs, design preferences with live samples,
// number of options, live combined preview, Kept / Will vary summary and soft warnings.
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { isHex, normHex, paletteFromBrand } from "@/lib/color";
import { clashes, emptyPreferences, inferPageType, summarize, wireframeRows } from "@/lib/logic";
import type { Palette, Preferences, Presets } from "@/lib/types";
import { FitBox, LivePreview } from "./LivePreview";
import { OptionCard, Section } from "./OptionCard";
import {
  BrandPalette, ColorSample, DensitySample, ImagerySample, MotionSample, ShapeSample, StyleSample,
  ThemeSample, TypographySample, Wireframe,
} from "./samples";

const NEUTRAL: Palette = { bg: "#F8FAFC", surface: "#FFFFFF", text: "#0F172A", muted: "#475569", primary: "#334155", on_primary: "#FFFFFF", accent: "#64748B", border: "#E2E8F0" };
const NEUTRAL_DARK: Palette = { bg: "#0B0F17", surface: "#131A26", text: "#E5E9F0", muted: "#9AA4B2", primary: "#CBD5E1", on_primary: "#0B0F17", accent: "#94A3B8", border: "#243042" };

export function SetupScreen() {
  const router = useRouter();
  const [presets, setPresets] = useState<Presets | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [prefs, setPrefs] = useState<Preferences>(emptyPreferences());
  const [count, setCount] = useState(3);
  const [densityTouched, setDensityTouched] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);
  const [brandInput, setBrandInput] = useState("#4F46E5");
  const [exampleIdx, setExampleIdx] = useState(0);
  const [remembered, setRemembered] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [mock, setMock] = useState(false);

  useEffect(() => {
    api.presets().then(setPresets).catch((e) => setError(`Can't reach the backend (${e.message}). Is it running on :8000?`));
    api.health().then((h) => setMock(h.mock)).catch(() => {});
    api.lastPreferences().then(({ preferences, candidate_count }) => {
      if (preferences) {
        setPrefs({ ...emptyPreferences(), ...preferences, page_type: null, product_name: null, product_description: null, sections: [],
          styles: preferences.styles.slice(0, 1), layouts: preferences.layouts.slice(0, 1) });
        setRemembered(true);
        if (preferences.color?.kind === "brand") { setBrandOpen(true); setBrandInput(preferences.color.value); }
        if (preferences.density) setDensityTouched(true);
      }
      if (candidate_count) setCount(candidate_count);
    }).catch(() => {});
  }, []);

  const set = <K extends keyof Preferences>(k: K, val: Preferences[K]) => setPrefs((p) => ({ ...p, [k]: val }));
  // No page-type picker: infer it from the description (the backend's intake makes the final call).
  const pageTypeId = inferPageType(prompt);
  const pageType = presets?.layouts.page_types.find((p) => p.id === pageTypeId) ?? null;
  const pageSectionIds = presets?.layouts.sections.filter((s) => s.page_types.includes(pageTypeId)).map((s) => s.id) ?? [];
  const sectionsTouched = prefs.sections.length > 0 && prefs.sections.every((id) => pageSectionIds.includes(id));
  const sections = sectionsTouched ? prefs.sections : pageType?.default_sections ?? [];

  // Smart default: pre-select the page type's recommended density until the developer picks one.
  useEffect(() => {
    if (!pageType || densityTouched) return;
    setPrefs((p) => ({ ...p, density: (pageType.recommended.density as Preferences["density"]) ?? null }));
  }, [pageType, densityTouched]);

  const theme = prefs.theme === "dark" ? "dark" : "light";
  const style = presets?.styles.styles.find((s) => s.id === prefs.styles[0]) ?? null;
  const direction = prefs.color?.kind === "direction" ? presets?.colors.directions.find((d) => d.id === prefs.color!.value) : undefined;
  const previewPalette: Palette = useMemo(() => {
    if (prefs.color?.kind === "brand" && isHex(prefs.color.value)) return paletteFromBrand(prefs.color.value, theme).palette;
    if (direction) return direction.examples[exampleIdx % direction.examples.length][theme];
    if (style && theme === "light") return { bg: style.sample.bg, surface: style.sample.bg, text: style.sample.text, muted: style.sample.muted, primary: style.sample.primary, on_primary: style.sample.onPrimary, accent: style.sample.accent, border: "rgba(127,127,127,.25)" };
    return theme === "dark" ? NEUTRAL_DARK : NEUTRAL;
  }, [prefs.color, direction, exampleIdx, style, theme]);

  if (error) return <div className="page"><div className="callout callout--error">{error}</div></div>;
  if (!presets) return <div className="page"><p className="muted">Loading options…</p></div>;

  const layouts = presets.layouts.layouts.filter((l) => l.page_type === pageTypeId);
  const pageSections = presets.layouts.sections.filter((s) => s.page_types.includes(pageTypeId));
  // A remembered layout from another page type doesn't apply to this page.
  const chosenLayouts = prefs.layouts.filter((id) => layouts.some((l) => l.id === id));
  const effective = { ...prefs, layouts: chosenLayouts };
  const previewLayout = layouts.find((l) => l.id === chosenLayouts[0]) ?? null;
  const warnings = clashes(effective, presets);
  const summary = summarize(effective, presets, count);
  const { min, max } = presets.options.candidate_count;

  const submit = async () => {
    if (!prompt.trim()) return;
    setSubmitting(true);
    try {
      const preferences = {
        ...effective, product_name: null, product_description: null,
        page_type: chosenLayouts.length ? pageTypeId : null,  // a chosen layout implies its page type
        sections: sectionsTouched ? prefs.sections : [],      // untouched: the agent picks sections
      };
      const body = { prompt, candidate_count: count, preferences };
      const { run_id } = await api.createRun(body);
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError(`Couldn't start the run: ${(e as Error).message}`);
      setSubmitting(false);
    }
  };

  return (
    <div className="setup">
      <div className="setup__main">
        <header className="page-head">
          <h1>Design a page</h1>
          <p>Describe the page, choose the look if you have opinions, and the agent handles the craft. Every option is optional.</p>
          {mock && <p className="note">Backend is in mock mode (UI_AGENT_MOCK=1): no API calls are made.</p>}
          {remembered && (
            <p className="note">Your last choices are pre-selected.{" "}
              <button className="link" onClick={() => { setPrefs(emptyPreferences()); setDensityTouched(false); setCount(3); setRemembered(false); setBrandOpen(false); }}>Reset to defaults</button>
            </p>
          )}
        </header>

        <Section title="What are you building?" id="prompt">
          <label className="field">
            <span>Describe the page</span>
            <textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)}
              placeholder="A landing page for Shipfast, a CI/CD tool for small teams. Main goal: start a free trial." />
          </label>
        </Section>

        <Section title="Style / mood" hint="Pick one, or leave it to the agent." id="style">
          <div className="grid grid--3">
            <OptionCard title="Let AI decide" selected={!prefs.styles.length} onSelect={() => set("styles", [])}
              sample={<div className="ai-sample">✦ Varies across options</div>} />
            {presets.styles.styles.map((s) => (
              <OptionCard key={s.id} title={s.name} hint={s.hint} selected={prefs.styles.includes(s.id)}
                onSelect={() => set("styles", [s.id])} sample={<StyleSample style={s} />} />
            ))}
          </div>
        </Section>

        <Section title="Layout" hint={`Pick one, or leave it to the agent. Showing layouts for a ${pageType?.name.toLowerCase() ?? "landing page"}, based on your description.`} id="layout">
          <div className="grid grid--3">
            <OptionCard title="Let AI decide" selected={!chosenLayouts.length} onSelect={() => set("layouts", [])}
              sample={<div className="ai-sample">✦ Varies across options</div>} />
            {layouts.map((l) => (
              <OptionCard key={l.id} title={l.name} hint={l.hint} selected={chosenLayouts.includes(l.id)}
                onSelect={() => set("layouts", [l.id])}
                sample={<Wireframe rows={wireframeRows(l, sections, presets)} shell={l.shell} unit={2} maxHeight={150} />} />
            ))}
          </div>
        </Section>

        <Section title="Color direction" hint="Choose a color family. The agent composes the exact combination and checks contrast." id="color">
          <div className="grid grid--3">
            <OptionCard title="Let AI decide" selected={!prefs.color} onSelect={() => { set("color", null); setBrandOpen(false); }}
              sample={<div className="ai-sample">✦ Varies across options</div>} />
            {presets.colors.directions.map((d) => (
              <OptionCard key={d.id} title={d.name} hint={d.hint}
                selected={prefs.color?.kind === "direction" && prefs.color.value === d.id}
                onSelect={() => { set("color", { kind: "direction", value: d.id }); setBrandOpen(false); setExampleIdx(0); }}
                sample={<ColorSample dir={d} theme={prefs.theme} />} />
            ))}
          </div>
          <div className="brand">
            <button className="link" aria-expanded={brandOpen} onClick={() => {
              const open = !brandOpen;
              setBrandOpen(open);
              if (open && isHex(brandInput)) set("color", { kind: "brand", value: normHex(brandInput) });
              if (!open && prefs.color?.kind === "brand") set("color", null);
            }}>{brandOpen ? "Use a color direction instead" : "Already have a brand color?"}</button>
            {brandOpen && (
              <div className="brand__panel">
                <p className="muted">Your brand color replaces the color direction. The agent builds the whole palette around it.</p>
                <div className="field-row">
                  <input type="color" aria-label="Brand color picker" value={isHex(brandInput) ? normHex(brandInput) : "#000000"}
                    onChange={(e) => { setBrandInput(e.target.value); set("color", { kind: "brand", value: normHex(e.target.value) }); }} />
                  <label className="field"><span>Hex</span>
                    <input value={brandInput} onChange={(e) => { setBrandInput(e.target.value); if (isHex(e.target.value)) set("color", { kind: "brand", value: normHex(e.target.value) }); }} /></label>
                </div>
                {isHex(brandInput) && <BrandPalette hex={normHex(brandInput)} theme={prefs.theme} />}
              </div>
            )}
          </div>
        </Section>

        <Section title="Theme" id="theme">
          <div className="grid grid--3">
            {presets.options.themes.map((t) => (
              <OptionCard key={t.id} title={t.name} hint={t.hint} selected={prefs.theme === t.id}
                onSelect={() => set("theme", t.id as Preferences["theme"])}
                sample={<ThemeSample theme={t.id} light={direction?.examples[0].light ?? NEUTRAL} dark={direction?.examples[0].dark ?? NEUTRAL_DARK} />} />
            ))}
          </div>
        </Section>

        <details className="more">
          <summary>More options <span className="muted">typography, density, shape, motion, imagery</span></summary>
          <Section title="Typography" id="typography">
            <div className="grid grid--3">
              <OptionCard title="Let AI decide" selected={!prefs.typography} onSelect={() => set("typography", null)} sample={<div className="ai-sample">✦ Varies across options</div>} />
              {presets.typography.pairings.map((t) => (
                <OptionCard key={t.id} title={t.name} hint={t.hint} selected={prefs.typography === t.id} onSelect={() => set("typography", t.id)}
                  sample={<TypographySample t={t} />} />
              ))}
            </div>
          </Section>
          <Section title="Density" id="density">
            <div className="grid grid--4">
              <OptionCard title="Let AI decide" selected={!prefs.density} onSelect={() => { set("density", null); setDensityTouched(true); }} sample={<div className="ai-sample">✦</div>} />
              {presets.options.density.map((d) => (
                <OptionCard key={d.id} title={d.name} hint={d.hint} selected={prefs.density === d.id}
                  badge={pageType?.recommended.density === d.id ? "Recommended" : undefined}
                  onSelect={() => { set("density", d.id as Preferences["density"]); setDensityTouched(true); }} sample={<DensitySample opt={d} />} />
              ))}
            </div>
            {pageType?.recommended.density && <p className="note">Recommended for a {pageType.name.toLowerCase()}: {presets.options.density.find((d) => d.id === pageType.recommended.density)?.hint}</p>}
          </Section>
          <Section title="Shape" id="shape">
            <div className="grid grid--4">
              <OptionCard title="Let AI decide" selected={!prefs.shape} onSelect={() => set("shape", null)} sample={<div className="ai-sample">✦</div>} />
              {presets.options.shapes.map((s) => (
                <OptionCard key={s.id} title={s.name} hint={s.hint} selected={prefs.shape === s.id} onSelect={() => set("shape", s.id as Preferences["shape"])} sample={<ShapeSample opt={s} />} />
              ))}
            </div>
          </Section>
          <Section title="Motion" id="motion">
            <div className="grid grid--4">
              <OptionCard title="Let AI decide" selected={!prefs.motion} onSelect={() => set("motion", null)} sample={<div className="ai-sample">✦</div>} />
              {presets.options.motion.map((m) => (
                <OptionCard key={m.id} title={m.name} hint={m.hint} selected={prefs.motion === m.id} onSelect={() => set("motion", m.id as Preferences["motion"])} sample={<MotionSample opt={m} />} />
              ))}
            </div>
          </Section>
          <Section title="Imagery" id="imagery">
            <div className="grid grid--5">
              <OptionCard title="Let AI decide" selected={!prefs.imagery} onSelect={() => set("imagery", null)} sample={<div className="ai-sample">✦</div>} />
              {presets.options.imagery.map((m) => (
                <OptionCard key={m.id} title={m.name} hint={m.hint} selected={prefs.imagery === m.id} onSelect={() => set("imagery", m.id as Preferences["imagery"])} sample={<ImagerySample opt={m} />} />
              ))}
            </div>
          </Section>
        </details>

        <Section title="Content" hint="Not about looks, but real content makes a much better design." id="content">
          <div className="field"><span>Tone of voice</span>
            <div className="grid grid--3">
              {presets.options.tones.map((t) => (
                <OptionCard key={t.id} title={t.name} hint={t.hint} selected={prefs.tone === t.id}
                  onSelect={() => set("tone", prefs.tone === t.id ? null : (t.id as Preferences["tone"]))}
                  sample={<div className="tone-sample">“{t.example}”</div>} />
              ))}
            </div>
          </div>
          <div className="field"><span>Sections</span>
            <div className="sections">
              {pageSections.map((s) => (
                <label key={s.id} className={`section-check ${sections.includes(s.id) ? "is-on" : ""}`}>
                  <input type="checkbox" checked={sections.includes(s.id)} onChange={() => {
                    const next = sections.includes(s.id) ? sections.filter((x) => x !== s.id) : [...sections, s.id];
                    set("sections", next);
                  }} />
                  <span className="section-check__icon"><Wireframe rows={s.rows.length ? s.rows : [{ h: 8, cols: [{ span: 6, k: "copy" }, { span: 6, k: "media" }] }]} unit={1.2} /></span>
                  {s.name}
                </label>
              ))}
            </div>
          </div>
          <label className="field"><span>Real copy (optional)</span>
            <textarea rows={4} value={prefs.copy ?? ""} onChange={(e) => set("copy", e.target.value || null)}
              placeholder="Paste headlines, feature descriptions, pricing… Real text produces much better designs than invented text." /></label>
        </Section>
      </div>

      <aside className="setup__aside" aria-label="Preview and generate">
        <div className="aside-card aside-card--preview">
          <div className="aside-card__head">
            <div>
              <h2>Preview of your choices</h2>
              <p className="caption caption--tight">Not the final design.</p>
            </div>
            {direction && <button className="chip" onClick={() => setExampleIdx((i) => i + 1)} title="Another combination">Another ↻</button>}
          </div>
          <FitBox><LivePreview prefs={prefs} presets={presets} palette={previewPalette} style={style} layout={previewLayout} /></FitBox>
        </div>

        <div className="aside-card">
          <p className="summary"><strong>Kept in all {count}:</strong> {summary.kept.join(", ") || "nothing yet"}</p>
          {summary.vary.length > 0 && <p className="summary"><strong>Will vary:</strong> {summary.vary.join(", ")}</p>}
          {warnings.map((w) => <p key={w} className="callout callout--warn">⚠ {w} You can continue anyway.</p>)}
          {summary.tooSimilar && <p className="callout callout--warn">⚠ With this many fixed choices, more than 3 options will look alike.</p>}
          <div className="generate-row">
            <div className="stepper" role="group" aria-label="Options to generate">
              <button aria-label="Fewer options" onClick={() => setCount((c) => Math.max(min, c - 1))} disabled={count <= min}>−</button>
              <output aria-live="polite">{count}</output>
              <button aria-label="More options" onClick={() => setCount((c) => Math.min(max, c + 1))} disabled={count >= max}>+</button>
            </div>
            <button className="btn btn--primary generate-row__btn" disabled={!prompt.trim() || submitting} onClick={submit}>
              {submitting ? "Starting…" : !prompt.trim() ? "Describe the page first" : `Generate ${count} option${count > 1 ? "s" : ""}`}
            </button>
          </div>
          <p className="caption caption--tight">Options to generate. Time and cost grow with the number.</p>
        </div>
      </aside>
    </div>
  );
}
