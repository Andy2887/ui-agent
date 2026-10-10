"""Schemas (plan §3.2, §5.9, §6.3).

Graph state holds plain JSON-able dicts (model.model_dump()) so checkpoints stay
portable; nodes validate into these models when they need typed access."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------
# Setup screen → run request
# --------------------------------------------------------------------------


class ColorChoice(BaseModel):
    """Color is one choice: a direction OR a brand color, never both (§5.2)."""

    kind: Literal["direction", "brand"]
    value: str  # direction id, or "#RRGGBB"


class DesignPreferences(BaseModel):
    page_type: Optional[str] = None  # landing / dashboard / pricing / auth / blog / portfolio
    styles: list[str] = Field(default_factory=list)  # at most 1; empty = let AI decide
    layouts: list[str] = Field(default_factory=list)  # at most 1; empty = let AI decide
    color: Optional[ColorChoice] = None  # None = let AI decide
    theme: Literal["light", "dark", "both"] = "light"
    typography: Optional[str] = None
    density: Optional[Literal["airy", "balanced", "compact"]] = None
    shape: Optional[Literal["sharp", "soft", "rounded"]] = None
    motion: Optional[Literal["none", "subtle", "expressive"]] = None
    imagery: Optional[Literal["illustrations", "photos", "abstract", "none"]] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    tone: Optional[Literal["professional", "friendly", "playful"]] = None
    sections: list[str] = Field(default_factory=list)
    copy_text: Optional[str] = Field(default=None, alias="copy")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _limits(self):
        if len(self.styles) > 1:
            raise ValueError("pick at most 1 style")
        if len(self.layouts) > 1:
            raise ValueError("pick at most 1 layout")
        return self


class RunRequest(BaseModel):
    prompt: str
    preferences: DesignPreferences = Field(default_factory=DesignPreferences)
    candidate_count: int = Field(3, ge=1, le=10)

    @model_validator(mode="after")
    def _layouts_fit(self):
        if len(self.preferences.layouts) > self.candidate_count:
            raise ValueError("pick at most as many layouts as options to generate")
        return self


# --------------------------------------------------------------------------
# LLM-facing structured outputs (no numeric/string constraints: see API limits)
# --------------------------------------------------------------------------


class IntakeResult(BaseModel):
    page_type: str
    audience: str
    product_name: str
    sections: list[str]
    assumptions: list[str]


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
    id: str  # short slug, e.g. "a", "b"
    name: str  # e.g. "Editorial Calm"
    description: str  # one plain-English line for the gallery
    slot: Literal["taste", "neutral", "wildcard"]
    reference_style: str
    layout_archetype: str
    layout_id: Optional[str]
    heading_font: str
    body_font: str
    palette: Palette
    dark_palette: Optional[Palette]
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
    details: str = ""
    items: list[dict] = Field(default_factory=list)


class AuditResult(BaseModel):
    passed: bool
    checks: list[CheckResult]

    def failing(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


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
    locked_preferences: dict[str, Any] = Field(default_factory=dict)


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
    prompt: str
    preferences: dict
    candidate_count: int
    intake: dict
    memory_context: dict
    regenerate_feedback: Optional[str]
    briefs: list[dict]
    candidates: Annotated[list[dict], candidates_reducer]
    selection: Optional[dict]  # {"id": ..., "notes": ...}
    rejected_ids: list[str]
    style_lock: Optional[dict]
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
