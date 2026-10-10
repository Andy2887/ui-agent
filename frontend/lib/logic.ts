import type { LayoutPreset, Palette, Preferences, Presets, StylePreset, WireRow } from "./types";

export const emptyPreferences = (): Preferences => ({
  page_type: null, styles: [], layouts: [], color: null, theme: "light", typography: null,
  density: null, shape: null, motion: null, imagery: null, product_name: null, product_description: null,
  tone: null, sections: [], copy: null,
});

const PAGE_TYPE_KEYWORDS: [string, RegExp][] = [
  ["dashboard", /\b(dashboard|admin|analytics|console|back[- ]?office)\b/i],
  ["pricing", /\bpricing\b|\bplans?\b.*\bprices?\b/i],
  ["auth", /\b(sign[- ]?up|sign[- ]?in|log[- ]?in|register|onboarding form)\b/i],
  ["blog", /\b(blog|article|post|newsletter issue)\b/i],
  ["portfolio", /\b(portfolio|personal site|case stud)/i],
];

/** Best-effort page type from the description, used only to pick which layouts and sections to show. */
export function inferPageType(prompt: string): string {
  return PAGE_TYPE_KEYWORDS.find(([, re]) => re.test(prompt))?.[0] ?? "landing";
}

/** Clash rules (§5.6): every key in `when` must match; arrays mean "all of these are picked". */
export function clashes(p: Preferences, presets: Presets): string[] {
  const value = (k: string): string[] => {
    switch (k) {
      case "styles": return p.styles;
      case "layouts": return p.layouts;
      case "color": return p.color?.kind === "direction" ? [p.color.value] : [];
      default: {
        const v = (p as unknown as Record<string, unknown>)[k];
        return typeof v === "string" ? [v] : [];
      }
    }
  };
  return presets.options.clash_rules
    .filter((r) => Object.entries(r.when).every(([k, want]) =>
      (Array.isArray(want) ? want : [want]).every((w) => value(k).includes(w))))
    .map((r) => r.reason);
}

export type Summary = { kept: string[]; vary: string[]; tooSimilar: boolean };

const nameOf = <T extends { id: string; name: string }>(list: T[], id: string | null) => list.find((x) => x.id === id)?.name ?? id ?? "";

/** "Kept in all N / Will vary" summary (§5.5). */
export function summarize(p: Preferences, presets: Presets, count: number): Summary {
  const kept: string[] = [];
  const vary: string[] = [];
  if (p.styles.length) kept.push(p.styles.map((s) => nameOf(presets.styles.styles, s)).join(" + "));
  else vary.push("style");
  if (p.color?.kind === "direction") { kept.push(nameOf(presets.colors.directions, p.color.value)); vary.push("exact colors"); }
  else if (p.color?.kind === "brand") kept.push(`brand color ${p.color.value}`);
  else vary.push("colors");
  kept.push(p.theme === "both" ? "light + dark" : p.theme === "dark" ? "Dark" : "Light");
  if (p.typography) kept.push(nameOf(presets.typography.pairings, p.typography)); else vary.push("typography");
  if (p.density) kept.push(nameOf(presets.options.density, p.density)); else vary.push("density");
  if (p.shape) kept.push(nameOf(presets.options.shapes, p.shape)); else vary.push("shape");
  if (p.motion) kept.push(`${nameOf(presets.options.motion, p.motion)} motion`); else vary.push("motion");
  if (p.imagery) kept.push(nameOf(presets.options.imagery, p.imagery)); else vary.push("imagery");

  if (p.layouts.length) kept.push(nameOf(presets.layouts.layouts, p.layouts[0])); else vary.push("layout");

  const fixed = [p.styles.length > 0, p.layouts.length > 0, p.color !== null, p.typography !== null, p.density !== null, p.shape !== null]
    .filter(Boolean).length;
  return { kept, vary, tooSimilar: fixed >= 4 && count > 3 };
}

/** Wireframe rows for a layout + checked sections (§5.2). */
export function wireframeRows(layout: LayoutPreset | null, sections: string[], presets: Presets): WireRow[] {
  const rows: WireRow[] = [];
  const shell = layout?.shell ?? "page";
  if (shell === "page") rows.push({ h: 3, cols: [{ span: 12, k: "nav" }] });
  rows.push(...(layout?.hero ?? [{ h: 14, cols: [{ span: 8, offset: 2, k: "copy-center" }] }]));
  for (const id of sections) {
    if (id === "hero") continue;
    const override = layout?.overrides?.[id];
    const sec = presets.layouts.sections.find((s) => s.id === id);
    rows.push(...(override ?? sec?.rows ?? []));
  }
  return rows;
}

/** CSS variables for the live combined preview, from presets alone (no LLM). */
export function previewVars(p: Preferences, presets: Presets, palette: Palette, style: StylePreset | null): Record<string, string> {
  const typo = presets.typography.pairings.find((t) => t.id === p.typography);
  const shape = presets.options.shapes.find((s) => s.id === (p.shape ?? null));
  const density = presets.options.density.find((d) => d.id === (p.density ?? "balanced"));
  const mult = (density?.space_multiplier as number) ?? 1;
  const headingFont = typo ? `"${typo.heading.family}", ${typo.heading.fallback}` : style ? `"${style.sample.headingFont}", system-ui` : "Inter, system-ui";
  const bodyFont = typo ? `"${typo.body.family}", ${typo.body.fallback}` : style ? `"${style.sample.bodyFont}", system-ui` : "Inter, system-ui";
  return {
    "--p-bg": palette.bg, "--p-surface": palette.surface, "--p-text": palette.text, "--p-muted": palette.muted,
    "--p-primary": palette.primary, "--p-on-primary": palette.on_primary, "--p-accent": palette.accent, "--p-border": palette.border,
    "--p-heading": headingFont, "--p-body": bodyFont,
    "--p-radius": (shape?.radius_md as string) ?? style?.sample.radius ?? "10px",
    "--p-radius-btn": (shape?.radius_button as string) ?? style?.sample.radius ?? "8px",
    "--p-shadow": (shape?.shadow as string) ?? style?.sample.shadow ?? "none",
    "--p-space": `${8 * mult}px`,
    "--p-heading-weight": String(style?.sample.headingWeight ?? 700),
    "--p-transform": style?.sample.uppercase ? "uppercase" : "none",
  };
}

export const SLOT_LABEL: Record<string, string> = {
  taste: "Based on your past picks", neutral: "Strong fit", wildcard: "Wildcard",
};

export const CRITERIA: Record<string, string> = {
  B1: "Visual hierarchy", B2: "Layout & spacing", B3: "Typography", B4: "Color", B5: "Responsive",
  B6: "Consistency", B7: "Content fit", B8: "Interaction states", B9: "Fidelity to your choices",
};

export const STOP_REASON: Record<string, string> = {
  pass: "Passed the quality bar",
  plateau: "Stopped improving, so we kept the best version",
  max_iters: "Reached the round limit, so we kept the best version",
  budget: "Reached the cost budget, so we kept the best version",
};
