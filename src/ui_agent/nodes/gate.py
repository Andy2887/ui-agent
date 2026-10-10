"""§8 gate: pure code. pass / revert / plateau / max_iters / budget / continue."""

from __future__ import annotations

from .. import settings
from ..llm import over_budget
from ..state import AgentState
from .common import emit


def _failing(d: dict) -> int:
    return sum(1 for c in (d.get("audit") or {}).get("checks", []) if not c["passed"])


def rank(d: dict) -> float:
    return (d.get("score") or 0) - 0.2 * _failing(d)


def passes(d: dict, issues: list[dict]) -> bool:
    cfg = settings.rubric()["pass"]
    scores = [s["score"] for s in (d.get("review") or {}).get("scores", [])]
    open_high = any(i["severity"] == "high" and i["status"] in ("open", "regressed") for i in issues)
    return bool((d.get("audit") or {}).get("passed")) and (d.get("score") or 0) >= cfg["weighted_average"] \
        and bool(scores) and min(scores) >= cfg["min_criterion"] and not open_high


def gate(state: AgentState) -> dict:
    cfg = settings.config()["refine"]
    cur, best = state["current"], state.get("best")
    issues = state.get("issues") or []
    iteration, cap = state.get("iteration", 0), state.get("iteration_cap", cfg["max_iterations"])
    new_best = cur if best is None or rank(cur) >= rank(best) else best
    best_scores = list(state.get("best_scores") or []) + [new_best.get("score") or 0]
    update: dict = {"best": new_best, "best_scores": best_scores}

    reopened_high = [i["id"] for i in issues if i["status"] == "regressed" and i["severity"] == "high"]
    decision, note = "continue", None
    if passes(cur, issues):
        decision = "pass"
        update["best"] = cur
    elif best is not None and ((cur.get("score") or 0) < (best.get("score") or 0) - cfg["regression_delta"] or reopened_high):
        note = (f"Score fell from {best.get('score')} to {cur.get('score')}" if not reopened_high
                else f"Previously fixed high-severity issue(s) came back: {', '.join(reopened_high)}") + \
               f". v{cur['version']} was reverted to v{best['version']}."
        update.update({"current": best, "regression_note": note, "best": best})
        update["best_scores"][-1] = best.get("score") or 0
        decision = "max_iters" if iteration >= cap else "revert"
    elif len(best_scores) > cfg["plateau_window"] and \
            best_scores[-1] - best_scores[-1 - cfg["plateau_window"]] < cfg["plateau_delta"]:
        decision = "plateau"
    elif iteration >= cap:
        decision = "max_iters"
    elif over_budget(state.get("usage")):
        decision = "budget"

    if decision not in ("continue", "revert"):
        update["stop_reason"] = decision
        update["current"] = update["best"]  # the output is always best, never just the latest
    update["gate_decision"] = decision
    emit("gate", decision=decision, note=note, iteration=iteration, score=cur.get("score"),
         best_version=update["best"]["version"], best_score=update["best"].get("score"))
    return update


def route_after_gate(state: AgentState) -> str:
    return "execute" if state.get("gate_decision") in ("continue", "revert") else "done"
