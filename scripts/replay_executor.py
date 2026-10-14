"""Replay the executor on recorded refine rounds, to compare executor variants on identical input.

    python scripts/replay_executor.py --label new runs/<id> [runs/<id> …]
    python scripts/replay_executor.py --label old --code /path/to/other/checkout runs/<id> … [--only <run>/v2,…]

For every refine round in each run (an `execute_started` that follows a gate), this rebuilds the executor's input
from disk (the HTML it started from, the issues it was given, the do-not-regress list, the StyleSpec and any
regression note), runs the executor from the checkout given by --code (default: this one), then renders and
audits the result. Only the executor and the browser run; there is no reviewer call, so issue-level quality is not
measured here. Results go to evals/replays/<stamp>-<label>/results.json."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rounds_of(run: Path) -> list[dict]:
    events = [json.loads(l) for l in (run / "events.jsonl").read_text().splitlines() if l.strip()]
    spec = next((e["spec"] for e in events if e["type"] == "style_locked"), None)
    out, last_review, gate = [], None, None
    for e in events:
        if e["type"] == "iteration":
            last_review = e["snapshot"]["version"]
        elif e["type"] == "gate":
            gate = e
        elif e["type"] == "execute_started" and gate and last_review:
            reverted = gate["decision"] == "revert"
            out.append({"version": e["version"], "issue_ids": e["issues"], "style_spec": spec,
                        "src_version": gate["best_version"] if reverted else last_review,
                        "reviewed_version": last_review, "regression_note": gate.get("note") if reverted else None})
            gate = None  # change-request rounds after final approval have no gate in front of them
    return out


def counting(cls):
    """Count views and failed edits on any TextEditor version (older ones do not track them)."""
    init, handle = cls.__init__, cls.handle

    def counted_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        self._replay_views = self._replay_failed = 0
        self._replay_errors = []
        cls.last = self

    def counted_handle(self, tool_input):
        ok, msg = handle(self, tool_input)
        self._replay_views += tool_input.get("command") == "view"
        self._replay_failed += not ok
        if not ok:
            self._replay_errors.append(f"{msg[:80]} | old_str starts {str(tool_input.get('old_str', ''))[:60]!r}")
        return ok, msg
    cls.__init__, cls.handle = counted_init, counted_handle


async def replay(a) -> None:
    out = ROOT / "evals" / "replays" / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.label}"
    out.mkdir(parents=True)
    os.environ["UI_AGENT_RUNS_DIR"] = str(out)
    code = Path(a.code).resolve() if a.code else ROOT
    os.environ["UI_AGENT_ROOT"] = str(code)  # prompts and config come from the same checkout as the code
    sys.path.insert(0, str(code / "src"))
    from ui_agent.nodes.executor import apply_fixes
    from ui_agent.nodes.gate import issues_after_revert
    from ui_agent.nodes.render import render_design
    from ui_agent.tools.browser import get_browser
    from ui_agent.tools.text_editor import TextEditor

    counting(TextEditor)
    results: list[dict] = []
    try:
        for run in map(Path, a.runs):
            events = [json.loads(l) for l in (run / "events.jsonl").read_text().splitlines() if l.strip()]
            recorded = {e["version"]: e for e in events if e["type"] == "audit"}
            started = {e["version"]: e["ts"] for e in events if e["type"] == "execute_started"}
            done = {e["version"]: e for e in events if e["type"] == "execute_done"}
            for r in rounds_of(run):
                key = f"{run.name}/v{r['version']}"
                if a.only and key not in a.only.split(","):
                    continue
                review = lambda v: json.loads((run / "refine" / f"v{v}-review.json").read_text())  # noqa: E731
                issues = review(r["reviewed_version"])["issues"]
                if r["src_version"] != r["reviewed_version"]:
                    issues = issues_after_revert({"review": review(r["src_version"])}, issues)
                by_id = {i["id"]: i for i in issues}
                given = [by_id[i] for i in r["issue_ids"] if i in by_id]
                resolved = [{"id": i["id"], "evidence": i["evidence"]} for i in issues if i["status"] == "resolved"]
                src_rel, dst_rel = f"refine/v{r['src_version']}.html", f"refine/v{r['version']}.html"
                (out / run.name / "refine").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(run / src_rel, out / run.name / src_rel)
                print(f"{key}: {len(given)} issues …", flush=True)
                t0 = time.time()
                summary, usage, _ = await apply_fixes(run.name, src_rel, dst_rel, given, style_spec=r["style_spec"],
                                                      do_not_regress=resolved, regression_note=r["regression_note"])
                seconds = time.time() - t0
                ed = TextEditor.last
                design, _ = await render_design(run.name, {"version": r["version"], "html_path": dst_rel},
                                                f"refine/v{r['version']}-shots")
                orig = recorded.get(r["version"]) or {}
                row = {
                    "round": key, "issues": len(given), "seconds": round(seconds, 1),
                    "turns": usage.get("calls"), "edits": ed.edits, "views": ed._replay_views,
                    "failed_edits": ed._replay_failed, "edit_errors": ed._replay_errors, "output_tokens": usage.get("output_tokens"),
                    "cost_usd": round(usage.get("cost_usd", 0.0), 4),
                    "audit_failures": [c["id"] for c in design["audit"]["checks"] if not c["passed"]],
                    "recorded_seconds": round(done[r["version"]]["ts"] - started[r["version"]], 1) if r["version"] in done else None,
                    "recorded_audit_failures": [c["id"] for c in orig.get("checks", []) if not c["passed"]],
                    "summary": summary,
                }
                results.append(row)
                (out / "results.json").write_text(json.dumps({"label": a.label, "code": str(code), "rounds": results}, indent=2))
                print(f"    {row['seconds']:.0f}s (recorded {row['recorded_seconds']}s)  turns {row['turns']}  edits {row['edits']}  "
                      f"views {row['views']}  failed {row['failed_edits']}  ${row['cost_usd']:.3f}  audit {row['audit_failures'] or 'pass'}",
                      flush=True)
    finally:
        await get_browser().close()
    n = len(results) or 1
    print(f"\nmean over {len(results)} rounds: {sum(r['seconds'] for r in results) / n:.0f}s  "
          f"turns {sum(r['turns'] or 0 for r in results) / n:.1f}  failed edits {sum(r['failed_edits'] for r in results) / n:.1f}  "
          f"total ${sum(r['cost_usd'] for r in results):.2f}\n{out / 'results.json'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--code", help="checkout whose executor to run (default: this one)")
    ap.add_argument("--only", help="comma-separated rounds, e.g. 20261011-134416-bae8/v2")
    asyncio.run(replay(ap.parse_args()))


if __name__ == "__main__":
    main()
