"""End-to-end graph run in mock mode: intake → kickoff → one direction → a sketch per page → approve → each page
designed and refined (key page first) → final approval → handoff."""

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
from ui_agent.nodes.common import root_tokens, run_dir  # noqa: E402
from ui_agent.tools.browser import get_browser  # noqa: E402

BRIEF = {"product_name": "Inkwell", "problem": "Independent writers can't turn one-off readers into subscribers",
         "flows": ["A reader finds the blog from a search, opens a post, reads it and signs up to get the next one."]}


async def _run(brief: dict, answers: dict | None = None, notes: str = "", revise: str | None = None,
               change: dict | None = None):
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

    await drive({"run_id": run_id, "user_id": "tester", "brief": brief, "usage": {}})
    if interrupts[-1]["kind"] == "kickoff":
        await drive(Command(resume={"action": "answer", "answers": answers or {}}))
    assert interrupts[-1]["kind"] == "sketch_review"
    if revise:
        await drive(Command(resume={"action": "revise", "feedback": revise}))
        assert interrupts[-1]["kind"] == "sketch_review"
    await drive(Command(resume={"action": "approve", "notes": notes}))
    assert interrupts[-1]["kind"] == "final_approval"
    if change:
        await drive(Command(resume={"action": "request_changes", **change}))
        assert interrupts[-1]["kind"] == "final_approval"
    await drive(Command(resume={"action": "approve"}))
    state = (await graph.aget_state(cfg)).values
    return run_id, state, events, interrupts


def test_flow_becomes_linked_pages_with_one_design_system():
    async def main():
        try:
            run_id, state, events, interrupts = await _run(BRIEF, answers={"q_audience": "Newsletter readers"})
            assert interrupts[0]["kind"] == "kickoff" and interrupts[0]["questions"][0]["id"] == "q_audience"
            assert state["intake"]["audience"] == "Newsletter readers" and not state["intake"]["questions"]
            pages = state["intake"]["pages"]
            assert [p["id"] for p in pages] == ["home", "post", "sign-up"]
            assert [p["file"] for p in pages] == ["index.html", "post.html", "sign-up.html"]
            assert [s["page"] for s in state["intake"]["flows"][0]["steps"]] == ["home", "post", "sign-up"]

            # One direction, one sketch per page, all shown at the review.
            review = interrupts[1]
            assert review["direction"]["id"] == "a" and len(review["pages"]) == 3
            assert all(p["sketch"].startswith("DESKTOP 1440px") for p in review["pages"])
            assert "-> sign-up" in review["pages"][1]["sketch"]
            assert (run_dir(run_id) / "sketches" / "post.txt").exists()

            # Key page first and alone; then the other pages run at the same time; every page refined until it passes.
            types = [e["type"] for e in events]
            assert types.count("style_locked") == 1
            started = [e["page_id"] for e in events if e["type"] == "design_started"]
            assert started[0] == "home" and set(started[1:]) == {"post", "sign-up"}
            order = [(e["type"], e["page_id"]) for e in events if e["type"] in ("page_started", "page_done")]
            assert order[:2] == [("page_started", "home"), ("page_done", "home")]
            assert {t for t, _ in order[2:4]} == {"page_started"}, order  # both start before either finishes
            assert all(state["pages"][p["id"]]["stop_reason"] == "pass" for p in pages), \
                {k: v["stop_reason"] for k, v in state["pages"].items()}
            fin = interrupts[-1]
            assert [p["id"] for p in fin["pages"]] == ["home", "post", "sign-up"]
            assert all(p["trajectory"][0]["score"] < p["trajectory"][-1]["score"] for p in fin["pages"])
            # Every page's final audit includes passing flow links.
            for p in fin["pages"]:
                a11 = next(c for c in p["final"]["audit"]["checks"] if c["id"] == "A11")
                assert a11["passed"], (p["id"], a11)

            out = run_dir(run_id) / "output"
            for f in ("index.html", "post.html", "sign-up.html", "tokens.json", "HANDOFF.md", "FLOWS.md",
                      "review-report.json", "screenshots/post/desktop.png", "history/home/v1.html", "pdf/index.pdf"):
                assert (out / f).exists(), f
            assert (run_dir(run_id) / "handoff.zip").exists()
            # One design system: every page carries the key page's tokens.
            key = root_tokens((out / "index.html").read_text())
            for f in ("post.html", "sign-up.html"):
                toks = root_tokens((out / f).read_text())
                assert all(toks.get(k) == v for k, v in key.items()), f
            assert 'href="sign-up.html"' in (out / "post.html").read_text()
            assert "`post.html`" in (out / "FLOWS.md").read_text()
            report = json.loads((out / "review-report.json").read_text())
            assert set(report["pages"]) == {"index.html", "post.html", "sign-up.html"}
            # history is not double-counted by the subgraph
            assert len(state["history"]) == sum(s["iteration"] for s in state["pages"].values())
        finally:
            await get_browser().close()
    asyncio.run(main())


def test_revise_then_notes_and_a_change_to_one_page():
    async def main():
        try:
            brief = {**BRIEF, "audience": "Readers of indie newsletters"}
            run_id, state, events, interrupts = await _run(brief, notes="less rounded", revise="Warmer, more personal",
                                                           change={"feedback": "Make the form shorter", "page_id": "sign-up"})
            assert interrupts[0]["kind"] == "sketch_review"
            first, second = interrupts[0]["direction"], interrupts[1]["direction"]
            assert first["name"] != second["name"] and state["rejected_directions"][0]["name"] == first["name"]
            for pid, page in state["pages"].items():
                ids = {i["id"]: i["status"] for i in page["issues"]}
                assert ids.get("chg_sketch_notes") == "resolved", pid
            changed = {i["id"]: i["status"] for i in state["pages"]["sign-up"]["issues"] if i["id"].startswith("chg_") and i["id"] != "chg_sketch_notes"}
            assert changed and set(changed.values()) == {"resolved"}
            assert not [i for i in state["pages"]["post"]["issues"] if i["id"] not in ("chg_sketch_notes",) and i["id"].startswith("chg_")]
            revisits = [e for e in events if e["type"] == "page_started" and e.get("revisit")]
            assert [e["page_id"] for e in revisits] == ["sign-up"]
        finally:
            await get_browser().close()
    asyncio.run(main())


def test_brief_without_flows_is_rejected():
    from pydantic import ValidationError

    from ui_agent.state import RunRequest
    try:
        RunRequest.model_validate({"brief": {"problem": "x", "flows": ["  "]}})
        raise AssertionError("expected a validation error")
    except ValidationError as e:
        assert "at least one user flow" in str(e)
