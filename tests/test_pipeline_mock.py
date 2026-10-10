"""End-to-end graph run in mock mode: intake → gallery → refine → approval → handoff."""

import asyncio
import json
import os
import uuid

os.environ["UI_AGENT_MOCK"] = "1"
os.environ.setdefault("UI_AGENT_RUNS_DIR", __import__("tempfile").mkdtemp(prefix="ui-agent-test-runs-"))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402
from langgraph.types import Command  # noqa: E402

from ui_agent.graph import build_graph  # noqa: E402
from ui_agent.nodes.common import run_dir  # noqa: E402
from ui_agent.tools.browser import get_browser  # noqa: E402


async def _run(count: int, prefs: dict, notes: str = "", change: str | None = None):
    graph = build_graph(InMemorySaver(), InMemoryStore())
    run_id = "test-" + uuid.uuid4().hex[:6]
    cfg = {"configurable": {"thread_id": run_id}}
    events, interrupts = [], []

    async def drive(inp):
        async for ns, mode, chunk in graph.astream(inp, cfg, stream_mode=["custom", "updates"], subgraphs=True):
            if mode == "custom":
                events.append(chunk)
            elif "__interrupt__" in chunk:
                interrupts.append(chunk["__interrupt__"][0].value)

    await drive({"run_id": run_id, "user_id": "tester", "prompt": "A landing page for Shipfast, a CI/CD tool for small teams",
                 "preferences": prefs, "candidate_count": count, "usage": {}})
    assert interrupts[-1]["kind"] == "gallery"
    assert len(interrupts[-1]["candidates"]) == count
    await drive(Command(resume={"action": "pick", "id": "a", "notes": notes}))
    assert interrupts[-1]["kind"] == "final_approval"
    if change:
        await drive(Command(resume={"action": "request_changes", "feedback": change}))
        assert interrupts[-1]["kind"] == "final_approval"
    await drive(Command(resume={"action": "approve"}))
    state = (await graph.aget_state(cfg)).values
    return run_id, state, events, interrupts


def test_full_run():
    async def main():
        try:
            run_id, state, events, interrupts = await _run(3, {"theme": "light", "styles": ["modern-saas"]})
            types = [e["type"] for e in events]
            assert types.count("candidate_ready") == 3
            assert state["stop_reason"] == "pass", state["stop_reason"]
            fin = interrupts[-1]
            assert fin["trajectory"][0]["score"] < fin["trajectory"][-1]["score"]
            out = run_dir(run_id) / "output"
            for f in ("index.html", "tokens.json", "HANDOFF.md", "review-report.json", "screenshots/desktop.png"):
                assert (out / f).exists(), f
            assert (run_dir(run_id) / "handoff.zip").exists()
            tokens = json.loads((out / "tokens.json").read_text())
            assert "color" in tokens and "primary" in tokens["color"]
            # history is not double-counted by the subgraph
            assert len(state["history"]) == state["iteration"]
            return state
        finally:
            await get_browser().close()
    state = asyncio.run(main())
    print("iterations", state["iteration"], "trajectory", [h["score"] for h in state["history"]])


def test_notes_and_change_request():
    async def main():
        try:
            run_id, state, events, interrupts = await _run(1, {"theme": "dark"}, notes="less rounded", change="Make the hero headline shorter")
            ids = {i["id"]: i["status"] for i in state["issues"]}
            assert ids.get("chg_gallery_notes") == "resolved"
            assert ids.get("chg_2") == "resolved"
        finally:
            await get_browser().close()
    asyncio.run(main())
