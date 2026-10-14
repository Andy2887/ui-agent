"""Internal dev tool (M1): run only the refine loop on an existing HTML file.

    python scripts/refine.py page.html --problem "Freelancers lose receipts" [--audience "Solo freelancers"] [--max-iters 5]

Writes everything under runs/<run_id>/refine/ and prints the score trajectory.
Set UI_AGENT_MOCK=1 to exercise the loop without API calls."""

import argparse
import asyncio
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ui_agent import settings  # noqa: E402
from ui_agent.nodes.common import root_tokens, run_dir  # noqa: E402
from ui_agent.refine_graph import build_refine_graph  # noqa: E402
from ui_agent.tools.browser import get_browser  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--problem", required=True)
    ap.add_argument("--audience", default="")
    ap.add_argument("--max-iters", type=int, default=settings.config()["refine"]["max_iterations"])
    a = ap.parse_args()
    run_id = "refine-" + time.strftime("%Y%m%d-%H%M%S")
    root = run_dir(run_id)
    (root / "refine").mkdir(exist_ok=True)
    shutil.copyfile(a.html, root / "refine" / "v1.html")
    html = Path(a.html).read_text()
    state = {
        "run_id": run_id, "user_id": "dev", "brief": {"problem": a.problem, "audience": a.audience}, "candidate_count": 1,
        "intake": {"page_type": "landing", "sections": [], "product_name": "", "problem": a.problem, "audience": a.audience,
                   "user_needs": [], "primary_action": "", "assumptions": [], "questions": []},
        "style_lock": {"direction_id": "given", "tokens": root_tokens(html), "character": "As given.",
                       "signature_elements": [], "must_keep": [], "user_notes": ""},
        "current": {"direction_id": "given", "version": 1, "html_path": "refine/v1.html"},
        "best": None, "iteration": 0, "iteration_cap": a.max_iters, "issues": [], "history": [], "usage": {},
    }
    try:
        out = await build_refine_graph().ainvoke(state, {"recursion_limit": 200})
    finally:
        await get_browser().close()
    for h in out["history"]:
        n_open = sum(1 for i in h["issues"] if i["status"] != "resolved")
        print(f"v{h['version']}: score {h['score']}  audit {'pass' if h['audit']['passed'] else 'fail'}  open issues {n_open}")
    print(f"\nstop: {out.get('stop_reason')}  best: v{out['best']['version']} ({out['best']['score']})  "
          f"cost: ${out.get('usage', {}).get('cost_usd', 0):.2f}\n{root / out['best']['html_path']}")


if __name__ == "__main__":
    asyncio.run(main())
