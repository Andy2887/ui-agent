"""Schemas (plan §3.2, §5.3, §6.3).

Graph state holds plain JSON-able dicts (model.model_dump()) so checkpoints stay
portable; nodes validate into these models when they need typed access."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------
# Brief screen → run request
# --------------------------------------------------------------------------


MAX_FLOWS = 5
MAX_PAGES = 6  # pages designed per run; intake lists any others as not designed


class ProductBrief(BaseModel):
    """What a PM tells a designer: the problem and what users do, and optionally more. Never the look or the pages."""

    problem: str  # what we're solving
    flows: list[str]  # user flows, one free-text paragraph each; the first is required
    audience: Optional[str] = None  # who it's for; the brief screen doesn't ask, so intake infers it
    product_name: Optional[str] = None
    context: Optional[str] = None  # constraints, existing brand, real copy, anything else

    @field_validator("problem")
    @classmethod
    def _required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("required")
        return v.strip()

    @field_validator("flows")
    @classmethod
    def _one_flow(cls, v: list[str]) -> list[str]:
        flows = [f.strip() for f in v if f and f.strip()]
        if not flows:
            raise ValueError("at least one user flow is required")
        if len(flows) > MAX_FLOWS:
            raise ValueError(f"at most {MAX_FLOWS} user flows")
        return flows


class RunRequest(BaseModel):
    brief: ProductBrief


def brief_text(brief: dict) -> str:
    """The PM's brief as plain text, for prompts and run lists."""
    labels = (("product_name", "Product"), ("problem", "Problem"), ("audience", "Users"), ("context", "Context"))
    lines = [f"{label}: {brief[k]}" for k, label in labels if brief.get(k)]
    lines += [f"User flow {i}: {f}" for i, f in enumerate(brief.get("flows") or [], 1)]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# LLM-facing structured outputs (no numeric/string constraints: see API limits)
# --------------------------------------------------------------------------


class KickoffQuestion(BaseModel):
    id: str  # short slug, e.g. "q_returning_users"
    question: str
    why: str  # how the answer changes the design, in plain words
    suggestions: list[str]  # likely answers the PM can pick with one click


class PagePlan(BaseModel):
    """One page of the site, worked out by the designer from the PM's flows."""

    id: str  # kebab-case, e.g. "post"
    name: str  # e.g. "Blog post"
    page_type: str  # closest library page type (landing, dashboard, pricing, auth, blog, portfolio)
    purpose: str  # what this page does for the user, in one sentence
    primary_action: str
    sections: list[str]
    links_to: list[str]  # ids of pages this page links to
    file: str = ""  # set by code: index.html for the entry page, <id>.html for the rest


class FlowStep(BaseModel):
    page: str  # page id
    action: str  # what the user does on that page at this step


class FlowPlan(BaseModel):
    name: str  # short, e.g. "Reader subscribes"
    steps: list[FlowStep]


class IntakeResult(BaseModel):
    product_name: str
    product_category: str  # e.g. "physiotherapy clinic"; looks up industry priors (library.py)
    problem: str  # restated as a design problem
    audience: str  # who they are, their context, what they already know
    user_needs: list[str]  # what the user must understand, feel or do across the site
    pages: list[PagePlan]  # the entry page of flow 1 first
    flows: list[FlowPlan]  # one per PM flow, in the same order
    assumptions: list[str]
    questions: list[KickoffQuestion]
    not_designed: list[str] = Field(default_factory=list)  # set by code: pages past MAX_PAGES


class Palette(BaseModel):
    bg: str
    surface: str
    text: str
    muted: str
    primary: str
    on_primary: str
    accent: str
    border: str


class DirectionBrief(BaseModel):
    """The site's design direction: a UX concept plus the visual mood (the design system) the designer proposes."""

    id: str  # set by code: "a"
    name: str  # e.g. "Snap and Forget"
    description: str  # one plain-English line for the sketch review
    slot: Literal["taste", "neutral"]  # taste: leans on the PM's remembered picks
    concept: str  # how this direction solves the problem for these users, across the flows
    tradeoff: str  # what it gives up
    layout_archetype: str  # how pages are composed, shared across the site
    layout_id: Optional[str]
    structure_id: Optional[str]  # page structure from the library for the entry page (presets/structures.json)
    variance: Literal["low", "mid", "high"]  # composition: centered/symmetric → conventional → asymmetric/bold
    style_id: Optional[str]  # reference style from the library; its recipe goes to the designer
    reference_style: str
    mood: list[str]  # 2–4 words, e.g. ["calm", "trustworthy"]
    theme: Literal["light", "dark"]
    heading_font: str
    body_font: str
    palette: Palette
    density: Literal["airy", "balanced", "compact"]
    shape: Literal["sharp", "soft", "rounded"]
    motion: Literal["none", "subtle", "expressive"]
    imagery: Literal["illustrations", "photos", "abstract", "none"]
    signature_element: str
    avoid: list[str]


class CriterionScore(BaseModel):
    criterion: Literal["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10"]
    score: int  # 1–5
    evidence: str


class Issue(BaseModel):
    id: str  # stable across rounds, e.g. "iss_hero_cta_contrast"
    criterion: str
    severity: Literal["high", "medium", "low"]
    selector: str
    viewport: Literal["mobile", "tablet", "desktop", "all"]
    evidence: str
    suggested_fix: str
    explanation: str  # plain English, for developers without design training
    status: Literal["open", "resolved", "regressed"]


class ReviewResult(BaseModel):
    summary: str
    scores: list[CriterionScore]
    issues: list[Issue]


# --------------------------------------------------------------------------
# Non-LLM records
# --------------------------------------------------------------------------


class CheckResult(BaseModel):
    id: str
    name: str
    passed: bool
    blocking: bool = True  # False: a warning the reviewer must address; never fails the audit
    details: str = ""
    items: list[dict] = Field(default_factory=list)
    fix: str = ""  # what to do instead, when the check knows better than "fix every item"


class AuditResult(BaseModel):
    passed: bool
    checks: list[CheckResult]

    def failing(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.blocking]


class Design(BaseModel):
    direction_id: str
    page_id: str = ""
    version: int
    html_path: str  # relative to the run dir
    screenshots: dict[str, str] = Field(default_factory=dict)  # viewport -> full-page png (relative)
    tiles: dict[str, list[str]] = Field(default_factory=dict)  # viewport -> tile pngs (relative)
    audit: Optional[dict] = None
    review: Optional[dict] = None
    score: Optional[float] = None
    error: Optional[str] = None


class StyleSpec(BaseModel):
    direction_id: str
    tokens: dict[str, str]  # parsed :root custom properties
    character: str
    signature_elements: list[str]
    must_keep: list[str]
    user_notes: str = ""


# --------------------------------------------------------------------------
# Graph state
# --------------------------------------------------------------------------


def sketches_reducer(left: list | None, right: list | None) -> list:
    """Fan-out reducer that also supports a reset (planner sends [{"__reset__": True}])."""
    left = left or []
    if right and any(isinstance(r, dict) and r.get("__reset__") for r in right):
        return [r for r in right if not (isinstance(r, dict) and r.get("__reset__"))]
    return left + (right or [])


def usage_reducer(left: dict | None, right: dict | None) -> dict:
    out = dict(left or {})
    for k, v in (right or {}).items():
        out[k] = out.get(k, 0) + v
    return out


class AgentState(TypedDict, total=False):
    run_id: str
    user_id: str
    brief: dict  # ProductBrief
    intake: dict  # IntakeResult: the pages and flows
    kickoff: Optional[dict]  # {"answers": [{"id", "question", "answer"}], "skipped": bool}
    memory_context: dict
    revise_feedback: Optional[str]  # the PM's feedback on the last direction and sketches
    direction: dict  # DirectionBrief
    rejected_directions: list[dict]  # directions the PM sent back, for taste memory
    sketches: Annotated[list[dict], sketches_reducer]  # one per page
    sketch_notes: str  # the PM's notes when approving the sketches
    style_lock: Optional[dict]  # from the key page (the first one designed); its tokens bind every page
    page_queue: list[str]  # page ids still to design, or to revisit with change requests
    pages: dict  # page id -> finished page: design (v1), best, issues, history state, stop_reason
    pending_changes: dict  # page id -> change requests from final review
    # The page in the refine loop right now. These keys are saved into `pages` when it finishes.
    page_id: Optional[str]
    design: Optional[dict]  # first full design of this page (refine v1)
    current: Optional[dict]
    best: Optional[dict]
    history: Annotated[list[dict], operator.add]
    iteration: int
    iteration_cap: int
    best_scores: list[float]  # best-so-far score after each review (plateau detection)
    issues: list[dict]  # all issues ever raised, latest status
    resolved_issue_ids: list[str]
    change_requests: list[dict]  # user feedback turned into high-severity issues
    change_requests_pending: bool
    gate_decision: Optional[str]
    regression_note: Optional[str]
    stop_reason: Optional[str]
    approved: bool
    handoff_dir: Optional[str]
    usage: Annotated[dict, usage_reducer]
