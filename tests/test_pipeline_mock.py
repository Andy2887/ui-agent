"""End-to-end graph run in mock mode: intake → kickoff → sketches → pick → design → refine → approval → handoff."""

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

BRIEF = {"product_name": "Shipfast", "problem": "Small teams waste hours babysitting flaky deploys",
         "audience": "Engineering leads at 5–20 person startups"}


async def _run(count: int, brief: dict, answers: dict | None = None, notes: str = "", change: str | None = None,
               mood_from: str | None = None):
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

    await drive({"run_id": run_id, "user_id": "tester", "brief": brief, "candidate_count": count, "usage": {}})
    if interrupts[-1]["kind"] == "kickoff":
        await drive(Command(resume={"action": "answer", "answers": answers or {}}))
    assert interrupts[-1]["kind"] == "gallery"
    assert len(interrupts[-1]["candidates"]) == count
    await drive(Command(resume={"action": "pick", "id": "a", "notes": notes, "mood_from": mood_from}))
    assert interrupts[-1]["kind"] == "final_approval"
    if change:
        await drive(Command(resume={"action": "request_changes", "feedback": change}))
        assert interrupts[-1]["kind"] == "final_approval"
    await drive(Command(resume={"action": "approve"}))
    state = (await graph.aget_state(cfg)).values
    return run_id, state, events, interrupts


def test_full_run_with_kickoff_answer():
    async def main():
        try:
            run_id, state, events, interrupts = await _run(3, BRIEF, answers={"q_primary_action": "Book a demo"})
            assert interrupts[0]["kind"] == "kickoff" and interrupts[0]["questions"][0]["id"] == "q_primary_action"
            assert state["intake"]["primary_action"] == "Book a demo" and not state["intake"]["questions"]
            types = [e["type"] for e in events]
            assert types.count("candidate_ready") == 3 and "design_ready" in types
            sketches = interrupts[1]["candidates"]
            assert all((run_dir(run_id) / c["screenshots"]["desktop"]).exists() for c in sketches)
            assert len({c["brief"]["concept"] for c in sketches}) == 3
            assert "data-sketch-kit" in (run_dir(run_id) / sketches[0]["html_path"]).read_text()
            assert state["stop_reason"] == "pass", state["stop_reason"]
            fin = interrupts[-1]
            assert fin["sketch"]["html_path"].startswith("sketches/") and fin["v1"]["html_path"] == "refine/v1.html"
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


def test_clear_brief_skips_kickoff_and_applies_notes():
    async def main():
        try:
            brief = {**BRIEF, "goal": "Start a free trial"}
            run_id, state, events, interrupts = await _run(1, brief, notes="less rounded", change="Make the hero headline shorter")
            assert [i["kind"] for i in interrupts][0] == "gallery"
            ids = {i["id"]: i["status"] for i in state["issues"]}
            assert ids.get("chg_gallery_notes") == "resolved"
            assert ids.get("chg_2") == "resolved"
        finally:
            await get_browser().close()
    asyncio.run(main())


def test_skipping_kickoff_questions_keeps_assumptions_and_mixes_moods():
    async def main():
        try:
            run_id, state, events, interrupts = await _run(2, BRIEF, answers={}, mood_from="b")
            assert state["kickoff"] == {"answers": [], "skipped": True}
            assert any("Primary action assumed" in a for a in state["intake"]["assumptions"])
            # Mix and match: A's structure wearing B's look.
            a, b = state["briefs"]
            final = (run_dir(run_id) / "output" / "index.html").read_text()
            assert b["heading_font"] in final and b["palette"]["primary"].lower() in final.lower()
            assert a["sections"][0] in final and state["selection"]["mood_from"] == "b"
        finally:
            await get_browser().close()
    asyncio.run(main())
