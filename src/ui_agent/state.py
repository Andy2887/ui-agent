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


class ProductBrief(BaseModel):
    """What a PM tells a designer: the problem, and optionally more. Never the look."""

    problem: str  # what we're solving
    audience: Optional[str] = None  # who it's for; the brief screen doesn't ask, so intake infers it
    product_name: Optional[str] = None
    goal: Optional[str] = None  # what a visitor should do or come away with
    context: Optional[str] = None  # constraints, existing brand, real copy, anything else

    @field_validator("problem")
    @classmethod
    def _required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("required")
        return v.strip()


class RunRequest(BaseModel):
    brief: ProductBrief
    candidate_count: int = Field(3, ge=1, le=10)


def brief_text(brief: dict) -> str:
    """The PM's brief as plain text, for prompts and run lists."""
    labels = (("product_name", "Product"), ("problem", "Problem"), ("audience", "Users"),
              ("goal", "Goal"), ("context", "Context"))
    return "\n".join(f"{label}: {brief[k]}" for k, label in labels if brief.get(k))


# --------------------------------------------------------------------------
# LLM-facing structured outputs (no numeric/string constraints: see API limits)
# --------------------------------------------------------------------------


class KickoffQuestion(BaseModel):
    id: str  # short slug, e.g. "q_returning_users"
    question: str
    why: str  # how the answer changes the design, in plain words
    suggestions: list[str]  # likely answers the PM can pick with one click


class IntakeResult(BaseModel):
    product_name: str
    page_type: str
    product_category: str  # e.g. "physiotherapy clinic"; looks up industry priors (library.py)
    problem: str  # restated as a design problem
    audience: str  # who they are, their context, what they already know
    user_needs: list[str]  # what the user must understand, feel or do on this page
    primary_action: str
    sections: list[str]
    assumptions: list[str]
    questions: list[KickoffQuestion]


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
    """One design direction: a UX concept plus the visual mood the designer proposes for it."""

    id: str  # short slug, e.g. "a", "b"
    name: str  # e.g. "Snap and Forget"
    description: str  # one plain-English line for the sketch gallery
    slot: Literal["taste", "neutral", "bold", "wildcard"]
    concept: str  # how this direction solves the problem for these users
    tradeoff: str  # what it gives up compared with other directions
    sections: list[str]  # page sections in order
    layout_archetype: str
    layout_id: Optional[str]
    structure_id: Optional[str]  # page structure from the library (presets/structures.json)
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


class PlanResult(BaseModel):
    briefs: list[DirectionBrief]


class StyleCharacter(BaseModel):
    character: str
    signature_elements: list[str]
    must_keep: list[str]


class CriterionScore(BaseModel):
    criterion: Literal["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]
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


class AuditResult(BaseModel):
    passed: bool
    checks: list[CheckResult]

    def failing(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.blocking]


class Design(BaseModel):
    direction_id: str
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


def candidates_reducer(left: list | None, right: list | None) -> list:
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
    candidate_count: int
    intake: dict
    kickoff: Optional[dict]  # {"answers": [{"id", "question", "answer"}], "skipped": bool}
    memory_context: dict
    regenerate_feedback: Optional[str]
    briefs: list[dict]
    candidates: Annotated[list[dict], candidates_reducer]  # sketches, one per brief
    selection: Optional[dict]  # {"id": ..., "notes": ..., "mood_from": direction id or None}
    rejected_ids: list[str]
    style_lock: Optional[dict]
    design: Optional[dict]  # first full design built from the chosen sketch (refine v1)
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
