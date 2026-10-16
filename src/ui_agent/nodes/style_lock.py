"""4.8 lock_style: StyleSpec from the approved direction plus the key page's first-design tokens, made once per run,
in code. Every page then starts its refine loop here with a fresh per-page state."""

from __future__ import annotations

from .. import settings
from ..state import AgentState, StyleSpec
from .common import emit, key_page_id, root_tokens, run_dir


def style_spec(direction: dict, tokens: dict[str, str], notes: str) -> dict:
    """The character comes from the direction the PM approved, not from a reading of the first render: the
    reviewer and executor then hold every page to that direction, and an unreviewed detail of v1 (a label above
    the headline, an icon tile) never becomes a rule. The tokens are v1's actual values."""
    d = direction
    character = (f"{d['name']}: {', '.join(d['mood'])}. {d['reference_style']} style, {d['theme']} theme, "
                 f"{d['density']} density, {d['shape']} shapes, {d['motion']} motion, {d['imagery']} imagery. "
                 f"Layout: {d['layout_archetype']}. Type: {d['heading_font']} headings over {d['body_font']} body text.")
    must_keep = [
        f"{d['theme'].capitalize()} theme",
        f"{d['heading_font']} for headings, {d['body_font']} for body text",
        f"{d['density'].capitalize()} density and {d['shape']} shapes",
        f"{d['motion'].capitalize()} motion",
    ] + [f"Avoid: {a}" for a in d.get("avoid") or []]
    return StyleSpec(direction_id=d["id"], tokens=tokens, character=character,
                     signature_elements=[d["signature_element"]], must_keep=must_keep, user_notes=notes).model_dump()


async def lock_style(state: AgentState) -> dict:
    pid = state["page_id"]
    notes = state.get("sketch_notes") or ""
    first = state["design"]
    direction = state["direction"]
    spec = state.get("style_lock")
    if spec is None:
        tokens = root_tokens((run_dir(state["run_id"]) / first["html_path"]).read_text())
        spec = style_spec(direction, tokens, notes)
        emit("style_locked", spec=spec)

    current = {"direction_id": direction["id"], "page_id": pid, "version": 1, "html_path": first["html_path"]}
    # The designer already applied the PM's notes; the reviewer verifies them like any other issue.
    issues = []
    if notes:
        issues.append({
            "id": "chg_sketch_notes", "criterion": "B9", "severity": "high", "selector": "body", "viewport": "all",
            "evidence": f"PM's note when approving the sketches: {notes}. It may concern only some pages; "
                        "mark it resolved when it is applied or doesn't apply to this page.",
            "suggested_fix": notes, "status": "open",
            "explanation": "You asked for this when you approved the sketches, so the reviewer checks it was applied.",
        })
    issues += [{**c, "status": "open"} for c in state.get("change_requests") or []]
    cfg = settings.config()["refine"]
    cap = cfg["max_iterations"] if pid == key_page_id(state) else cfg.get("max_iterations_secondary", cfg["max_iterations"])
    return {
        "style_lock": spec, "current": current, "best": None, "iteration": 0, "iteration_cap": int(cap),
        "issues": issues, "change_requests": issues, "resolved_issue_ids": [], "best_scores": [],
        "stop_reason": None, "regression_note": None, "gate_decision": None,
        "change_requests_pending": False,
    }
