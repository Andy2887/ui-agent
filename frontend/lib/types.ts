export type Palette = {
  bg: string; surface: string; text: string; muted: string;
  primary: string; on_primary: string; accent: string; border: string;
};

export type StylePreset = {
  id: string; name: string; hint: string; guidance: string;
  sample: {
    bg: string; text: string; muted: string; primary: string; onPrimary: string; accent: string;
    headingFont: string; bodyFont: string; headingWeight: number; radius: string; border: string;
    shadow: string; deco: string; uppercase: boolean;
  };
};

export type WireCol = { span: number; offset?: number; k: string };
export type WireRow = { h: number; cols: WireCol[] };

export type LayoutPreset = {
  id: string; page_type: string; name: string; hint: string; brief: string;
  shell: "page" | "sidebar" | "split-list"; hero: WireRow[]; overrides: Record<string, WireRow[]>;
};

export type SectionPreset = { id: string; name: string; page_types: string[]; rows: WireRow[] };
export type PageType = { id: string; name: string; default_sections: string[]; recommended: { density?: string } };

export type ColorDirection = {
  id: string; name: string; hint: string; swatches: string[];
  ranges: Record<string, unknown>;
  examples: { light: Palette; dark: Palette }[];
};

export type FontSpec = { family: string; weights: number[]; fallback: string; letter_spacing?: string };
export type TypographyPreset = { id: string; name: string; hint: string; heading: FontSpec; body: FontSpec; scale_ratio: number; google: string };

export type SimpleOption = { id: string; name: string; hint: string; [k: string]: unknown };

export type ClashRule = { when: Record<string, string | string[]>; reason: string };

export type Presets = {
  styles: { max_picks: number; styles: StylePreset[] };
  layouts: { page_types: PageType[]; sections: SectionPreset[]; layouts: LayoutPreset[] };
  colors: { directions: ColorDirection[] };
  typography: { pairings: TypographyPreset[] };
  options: {
    themes: SimpleOption[]; density: SimpleOption[]; shapes: SimpleOption[]; motion: SimpleOption[];
    imagery: SimpleOption[]; tones: (SimpleOption & { example: string })[];
    candidate_count: { default: number; min: number; max: number };
    clash_rules: ClashRule[];
  };
};

export type ColorChoice = { kind: "direction" | "brand"; value: string } | null;

export type Preferences = {
  page_type: string | null;
  styles: string[];
  layouts: string[];
  color: ColorChoice;
  theme: "light" | "dark" | "both";
  typography: string | null;
  density: "airy" | "balanced" | "compact" | null;
  shape: "sharp" | "soft" | "rounded" | null;
  motion: "none" | "subtle" | "expressive" | null;
  imagery: "illustrations" | "photos" | "abstract" | "none" | null;
  product_name: string | null;
  product_description: string | null;
  tone: "professional" | "friendly" | "playful" | null;
  sections: string[];
  copy: string | null;
};

export type CheckSummary = { id: string; name: string; passed: boolean; details: string };

export type Issue = {
  id: string; criterion: string; severity: "high" | "medium" | "low"; selector: string; viewport: string;
  evidence: string; suggested_fix: string; explanation: string; status: "open" | "resolved" | "regressed";
};

export type Score = { criterion: string; score: number; evidence: string };

export type Brief = {
  id: string; name: string; description: string; slot: "taste" | "neutral" | "wildcard";
  reference_style: string; layout_archetype: string; layout_id: string | null;
  heading_font: string; body_font: string; palette: Palette; dark_palette: Palette | null;
  density: string; shape: string; motion: string; imagery: string; signature_element: string; avoid: string[];
};

export type Design = {
  direction_id: string; version: number; html_path: string;
  screenshots?: Record<string, string>; tiles?: Record<string, string[]>;
  audit?: { passed: boolean; checks: (CheckSummary & { items: unknown[] })[] };
  score?: number | null; error?: string | null;
};

export type Snapshot = {
  version: number; html_path: string; screenshots: Record<string, string>; score: number | null;
  scores: Score[]; issues: Issue[]; summary: string | null;
  audit: { passed: boolean | null; checks: CheckSummary[] }; executor_summary?: string | null;
};

export type GalleryCandidate = {
  id: string; name: string; description: string; slot: string; html_path: string;
  screenshots: Record<string, string>; error: string | null; audit: CheckSummary[]; brief: Brief;
};

export type RunEvent = { seq: number; ts: number; type: string; [k: string]: any };
