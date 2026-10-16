"""Eval harness (plan §13): run the full pipeline headless on the fixed briefs and record quality, cost and time.

    python scripts/eval.py run --label baseline [--only clinic-booking,vague-shop] [--max-usd 4] [--stop-after design]
    python scripts/eval.py compare evals/results/<a> evals/results/<b>

The PM is simulated: kickoff questions get their first suggested answer, the sketches are approved with no
notes, and the final site is approved. Memory is in-process, so eval runs neither read nor change the real
taste profile or lessons. Each run's artifacts and events.jsonl go to evals/results/<stamp>-<label>/<brief id>/,
and the per-brief metrics go to results.json in that folder. `--stop-after design` ends each run at the key page's first
full design (about $0.15 a brief), for changes that only affect v1. Scores are per site: the mean of the pages' best
scores; "v1" is the key page's first design, so it stays comparable with single-page results. Set UI_AGENT_MOCK=1 for a free smoke test."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ROLES = ("intake", "planner", "sketcher", "generator", "reviewer", "executor", "handoff")
STOP_NODES = {"design": "design_page"}


def git_rev() -> str:
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return rev + ("+dirty" if dirty else "")


def auto_answer(interrupt: dict) -> dict:
    kind = interrupt["kind"]
    if kind == "kickoff":
        return {"action": "answer", "answers": {q["id"]: q["suggestions"][0] for q in interrupt["questions"] if q.get("suggestions")}}
    if kind == "sketch_review":
        return {"action": "approve", "notes": ""}
    if kind == "final_approval":
        return {"action": "approve"}
    raise ValueError(f"unexpected interrupt {kind!r}")


async def run_brief(case: dict, stop_after: str | None = None) -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore
    from langgraph.types import Command

    from ui_agent.graph import build_graph
    from ui_agent.nodes.common import run_dir

    run_id = case["id"]
    graph = build_graph(InMemorySaver(), InMemoryStore())
    cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 200}
    log = (run_dir(run_id) / "events.jsonl").open("w")
    events: list[dict] = []

    def record(e: dict) -> None:
        e = {"seq": len(events), "ts": e.get("ts", time.time()), **e}
        events.append(e)
        log.write(json.dumps(e, default=str) + "\n")

    record({"type": "status", "status": "running", "request": {"brief": case["brief"]}})
    t0, inp, error = time.time(), {"run_id": run_id, "user_id": "eval", "brief": case["brief"], "usage": {}}, None
    try:
        while True:
            interrupted = None
            async for _ns, mode, chunk in graph.astream(inp, cfg, stream_mode=["custom", "updates"], subgraphs=True,
                                                        interrupt_after=[STOP_NODES[stop_after]] if stop_after else None):
                if mode == "custom":
                    record(chunk)
                elif chunk.get("__interrupt__"):  # empty for the --stop-after breakpoint, which ends the run
                    interrupted = chunk["__interrupt__"][0].value
            if not interrupted:
                break
            answer = auto_answer(interrupted)
            record({"type": "interrupt", "kind": interrupted["kind"]})
            record({"type": "resume", "answer": answer})
            inp = Command(resume=answer)
    except Exception as e:  # one broken brief must not lose the others' results
        error = f"{type(e).__name__}: {e}"
    state = (await graph.aget_state(cfg)).values
    record({"type": "status", "status": "error" if error else "done", "error": error})
    log.close()
    return summarize(case["id"], state, events, time.time() - t0, error)


def summarize(case_id: str, state: dict, events: list[dict], wall: float, error: str | None) -> dict:
    from ui_agent.nodes.memory_nodes import site_score

    # Usage comes from the final state, not events.jsonl, where refine's node_done repeats review/execute usage.
    usage = state.get("usage") or {}
    history = state.get("history") or []
    site = (state.get("intake") or {}).get("pages") or []
    key = site[0]["id"] if site else None
    v1 = next((h for h in history if h.get("page_id") == key), None) or state.get("design") or {}
    saved = state.get("pages") or {}
    pages = {pid: {"stop_reason": s.get("stop_reason") or s.get("skipped"), "iterations": s.get("iteration"),
                   "final_score": (s.get("best") or {}).get("score"),
                   "trajectory": [h.get("score") for h in history if h.get("page_id") == pid]}
             for pid, s in saved.items()}
    stops = {p["stop_reason"] for p in pages.values()}
    by_type = lambda t: [e for e in events if e["type"] == t]  # noqa: E731
    starts = {(e.get("page_id"), e["version"]): e["ts"] for e in by_type("execute_started")}
    rounds = [{"page_id": e.get("page_id"), "version": e["version"], "seconds": round(e["ts"] - starts[(e.get("page_id"), e["version"])], 1),
               **{k: e.get(k) for k in ("edits", "views", "failed_edits", "turns", "edit_errors")}}
              for e in by_type("execute_done") if (e.get("page_id"), e["version"]) in starts]
    renders, gates = by_type("render_started"), by_type("gate")
    return {
        "id": case_id, "error": error,
        "stop_reason": ("pass" if stops == {"pass"} else ",".join(sorted(str(x) for x in stops))) if pages else state.get("stop_reason"),
        "kickoff_asked": any(e["kind"] == "kickoff" for e in by_type("interrupt")),
        "page_count": len(site), "pages_passed": sum(p["stop_reason"] == "pass" for p in pages.values()),
        "iterations": sum(p["iterations"] or 0 for p in pages.values()) or state.get("iteration", 0),
        "v1_audit_passed": (v1.get("audit") or {}).get("passed"),
        "v1_audit_failures": [c["id"] for c in (v1.get("audit") or {}).get("checks", []) if not c["passed"]],
        "v1_audit_details": {c["id"]: c["details"] for c in (v1.get("audit") or {}).get("checks", []) if not c["passed"]},
        "v1_score": v1.get("score"),
        "trajectory": [h.get("score") for h in history if h.get("page_id") == key],
        "final_score": site_score(state) if pages else (state.get("best") or {}).get("score"),
        "pages": pages,
        "cost_usd": round(usage.get("cost_usd", 0.0), 4),
        "cost_by_role": {r: round(usage.get(f"{r}.cost_usd", 0.0), 4) for r in ROLES if usage.get(f"{r}.cost_usd")},
        "seconds": round(wall, 1),
        "refine_seconds": round(gates[-1]["ts"] - renders[0]["ts"], 1) if renders and gates else None,
        "executor_seconds": round(sum(r["seconds"] for r in rounds), 1),
        "executor_rounds": rounds,
    }


async def cmd_run(a) -> None:
    import yaml

    cases = yaml.safe_load((ROOT / "evals" / "briefs.yaml").read_text())["briefs"]
    if a.only:
        wanted = set(a.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    out = ROOT / "evals" / "results" / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.label}"
    out.mkdir(parents=True)
    os.environ["UI_AGENT_RUNS_DIR"] = str(out)
    from ui_agent import settings
    from ui_agent.tools.browser import get_browser

    meta = {"label": a.label, "git": git_rev(), "mock": settings.mock_mode(), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models": settings.config()["models"], "refine": settings.config()["refine"], "stop_after": a.stop_after}
    results: list[dict] = []
    spent = 0.0
    try:
        for case in cases:
            if spent >= a.max_usd:
                print(f"skipping {case['id']}: ${spent:.2f} spent, cap is ${a.max_usd:.2f}")
                continue
            print(f"[{len(results) + 1}/{len(cases)}] {case['id']} …", flush=True)
            r = await run_brief(case, a.stop_after)
            spent += r["cost_usd"]
            results.append(r)
            (out / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
            print(f"    {r['stop_reason'] or r['error']}  iters {r['iterations']}  score {r['final_score']}  "
                  f"${r['cost_usd']:.2f}  {r['seconds']:.0f}s  (total ${spent:.2f})", flush=True)
    finally:
        await get_browser().close()
    print_table(results)
    print(f"\n{out / 'results.json'}")


# ------------------------------------------------------------------ reporting
METRICS = [  # (label, function over one result)
    ("v1 audit pass", lambda r: float(bool(r["v1_audit_passed"]))),
    ("v1 score", lambda r: r["v1_score"]),
    ("final score", lambda r: r["final_score"]),
    ("passed gate", lambda r: float(r["stop_reason"] == "pass")),
    ("pages", lambda r: r.get("page_count")),
    ("page pass rate", lambda r: r["pages_passed"] / r["page_count"] if r.get("page_count") else None),
    ("iterations", lambda r: r["iterations"]),
    ("cost $", lambda r: r["cost_usd"]),
    ("seconds", lambda r: r["seconds"]),
    ("refine s", lambda r: r["refine_seconds"]),
    ("executor s / round", lambda r: _per_round(r, "seconds")),
    ("executor turns / round", lambda r: _per_round(r, "turns")),
    ("failed edits / round", lambda r: _per_round(r, "failed_edits")),
]


def _per_round(r: dict, key: str) -> float | None:
    vals = [x[key] for x in r["executor_rounds"] if x.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def _mean(results: list[dict], fn) -> float | None:
    vals = [v for v in (fn(r) for r in results if not r["error"]) if v is not None]
    return statistics.mean(vals) if vals else None


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def print_table(results: list[dict]) -> None:
    print(f"\n{'brief':22} {'stop':10} {'iters':>5} {'v1 audit':>9} {'v1':>5} {'final':>6} {'$':>6} {'sec':>5} {'exec s/rd':>9} {'turns/rd':>8}")
    for r in results:
        print(f"{r['id']:22} {'ERROR' if r['error'] else str(r['stop_reason'] or 'stopped'):10} {r['iterations']:>5} "
              f"{'pass' if r['v1_audit_passed'] else ','.join(r['v1_audit_failures']) or '—':>9} "
              f"{_fmt(r['v1_score']):>5} {_fmt(r['final_score']):>6} {r['cost_usd']:>6.2f} {r['seconds']:>5.0f} "
              f"{_fmt(_per_round(r, 'seconds')):>9} {_fmt(_per_round(r, 'turns')):>8}")
    print("\nmean: " + "  ".join(f"{label} {_fmt(_mean(results, fn))}" for label, fn in METRICS))


def cmd_compare(a) -> None:
    sets = [json.loads((Path(d) / "results.json").read_text()) for d in (a.a, a.b)]
    print(f"{'metric':24} {sets[0]['meta']['label'][:14]:>14} {sets[1]['meta']['label'][:14]:>14} {'delta':>8}")
    for label, fn in METRICS:
        x, y = (_mean(s["results"], fn) for s in sets)
        print(f"{label:24} {_fmt(x):>14} {_fmt(y):>14} {_fmt(y - x) if x is not None and y is not None else '—':>8}")
    print("\nReviewer scores are noisy (|Δ| 0.1–0.28 on identical input); treat score deltas below that as no change.")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--only", help="comma-separated brief ids")
    r.add_argument("--max-usd", type=float, default=5.0, help="stop starting new briefs once this much is spent")
    r.add_argument("--stop-after", choices=["design"], help="end each run after this node")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    a = ap.parse_args()
    if a.cmd == "run":
        asyncio.run(cmd_run(a))
    else:
        cmd_compare(a)


if __name__ == "__main__":
    main()
