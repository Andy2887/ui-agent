export type Palette = {
  bg: string; surface: string; text: string; muted: string;
  primary: string; on_primary: string; accent: string; border: string;
};

/** What the PM tells the designer: the problem and the people, never the look. */
export type ProductBrief = {
  problem: string; audience: string;
  product_name?: string | null; goal?: string | null; context?: string | null;
};

export type KickoffQuestion = { id: string; question: string; why: string; suggestions: string[] };

/** The designer's reading of the brief. */
export type DesignBrief = {
  product_name: string; page_type: string; problem: string; audience: string; user_needs: string[];
  primary_action: string; sections: string[]; assumptions: string[]; questions?: KickoffQuestion[];
};

/** blocking=false: a warning (A9 layout balance) the reviewer must address, but it never fails the audit. */
export type CheckSummary = { id: string; name: string; passed: boolean; blocking?: boolean; details: string };

export type Issue = {
  id: string; criterion: string; severity: "high" | "medium" | "low"; selector: string; viewport: string;
  evidence: string; suggested_fix: string; explanation: string; status: "open" | "resolved" | "regressed";
};

export type Score = { criterion: string; score: number; evidence: string };

/** One direction: a UX concept plus the visual mood the designer proposes. */
export type Brief = {
  id: string; name: string; description: string; slot: "taste" | "neutral" | "bold" | "wildcard";
  concept: string; tradeoff: string; sections: string[];
  layout_archetype: string; layout_id: string | null; structure_id: string | null; variance: "low" | "mid" | "high";
  style_id: string | null; reference_style: string;
  mood: string[]; theme: "light" | "dark"; heading_font: string; body_font: string; palette: Palette;
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
  screenshots: Record<string, string>; error: string | null; brief: Brief;
};

export type RunEvent = { seq: number; ts: number; type: string; [k: string]: any };
