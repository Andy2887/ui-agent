export type Palette = {
  bg: string; surface: string; text: string; muted: string;
  primary: string; on_primary: string; accent: string; border: string;
};

/** What the PM tells the designer: the problem and what users do (one free-text paragraph per flow), never the look or the pages. */
export type ProductBrief = {
  problem: string; flows: string[]; audience?: string | null;
  product_name?: string | null; context?: string | null;
};

export type KickoffQuestion = { id: string; question: string; why: string; suggestions: string[] };

/** One page of the site, worked out by the designer from the flows. `file` is what the pages link to. */
export type PagePlan = {
  id: string; name: string; page_type: string; purpose: string; primary_action: string;
  sections: string[]; links_to: string[]; file: string;
};

export type FlowPlan = { name: string; steps: { page: string; action: string }[] };

/** The designer's reading of the brief: who it's for, and the site map. */
export type DesignBrief = {
  product_name: string; problem: string; audience: string; user_needs: string[];
  pages: PagePlan[]; flows: FlowPlan[]; not_designed?: string[];
  assumptions: string[]; questions?: KickoffQuestion[];
};

/** blocking=false: a warning (A9 layout balance, A10 AI-template tells) the reviewer must address, but it never fails the audit. */
export type CheckSummary = { id: string; name: string; passed: boolean; blocking?: boolean; details: string };

export type Issue = {
  id: string; criterion: string; severity: "high" | "medium" | "low"; selector: string; viewport: string;
  evidence: string; suggested_fix: string; explanation: string; status: "open" | "resolved" | "regressed";
};

export type Score = { criterion: string; score: number; evidence: string };

/** The site's direction: a UX concept plus the design system the designer proposes. */
export type Brief = {
  id: string; name: string; description: string; slot: "taste" | "neutral";
  concept: string; tradeoff: string;
  layout_archetype: string; layout_id: string | null; structure_id: string | null; variance: "low" | "mid" | "high";
  style_id: string | null; reference_style: string;
  mood: string[]; theme: "light" | "dark"; heading_font: string; body_font: string; palette: Palette;
  density: string; shape: string; motion: string; imagery: string; signature_element: string; avoid: string[];
};

export type Design = {
  direction_id: string; page_id: string; version: number; html_path: string;
  screenshots?: Record<string, string>; tiles?: Record<string, string[]>;
  audit?: { passed: boolean; checks: (CheckSummary & { items: unknown[] })[] };
  score?: number | null; error?: string | null;
};

export type Snapshot = {
  page_id: string | null; version: number; html_path: string; screenshots: Record<string, string>; score: number | null;
  scores: Score[]; issues: Issue[]; summary: string | null;
  audit: { passed: boolean | null; checks: CheckSummary[] }; executor_summary?: string | null;
};

/** A low-fi sketch of one page: a plain-text wireframe (DESKTOP chart, MOBILE reflow lines, NOTES). */
export type Sketch = { page_id: string; direction_id: string; sketch_path: string; text?: string; error?: string | null };

/** What the PM reviews before anything is designed: the direction and every page's sketch. */
export type SketchReview = { design_brief: DesignBrief; direction: Brief; pages: (PagePlan & { sketch: string; error: string | null })[] };

/** One page at final review. `final` and friends are missing when the page was skipped (budget). */
export type FinalPage = {
  id: string; name: string; file: string; purpose: string; sketch: string; skipped?: string | null;
  v1?: { version: number; html_path: string; screenshots: Record<string, string> };
  final?: Snapshot; trajectory?: { version: number; score: number | null; open_issues: number }[];
  remaining_issues?: Issue[]; stop_reason?: string | null;
};

export type FinalApproval = { pages: FinalPage[]; flows: FlowPlan[]; not_designed: string[]; site_dir: string; usage?: Record<string, number> };

export type RunEvent = { seq: number; ts: number; type: string; [k: string]: any };
