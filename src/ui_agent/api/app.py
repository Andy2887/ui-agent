"""FastAPI backend (plan §3.3). Run with:  uvicorn ui_agent.api.app:app --reload"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore
from pydantic import BaseModel, ValidationError

from .. import settings
from ..graph import build_graph
from ..memory import store as memory
from ..state import RunRequest
from ..tools.browser import get_browser
from .runs import RunManager

USER_ID = "local"  # v1 is single-user


@asynccontextmanager
async def lifespan(app: FastAPI):
    data = settings.data_dir()
    async with AsyncSqliteSaver.from_conn_string(str(data / "checkpoints.sqlite")) as saver, \
            AsyncSqliteStore.from_conn_string(str(data / "memory.sqlite")) as store:
        await store.setup()
        app.state.store = store
        app.state.runs = RunManager(build_graph(checkpointer=saver, store=store))
        yield
        await get_browser().close()


app = FastAPI(title="UI Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("UI_AGENT_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True, "mock": settings.mock_mode(),
            "models": {k: v["model"] for k, v in settings.config()["models"].items()}}


@app.get("/presets")
async def presets():
    return settings.presets()


@app.post("/runs")
async def create_run(body: dict):
    try:
        req = RunRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False))
    run_id = await app.state.runs.start(req.model_dump(mode="json"), USER_ID)
    return {"run_id": run_id}


@app.get("/runs")
async def list_runs():
    return app.state.runs.list()


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    h = app.state.runs.get(run_id)
    if not h:
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "status": h.status, "events": len(h.events)}


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, since: int = 0):
    """Server-sent events: replays everything after `since`, then streams live."""
    h = app.state.runs.get(run_id)
    if not h:
        raise HTTPException(404, "run not found")
    q: asyncio.Queue = asyncio.Queue()
    h.subscribers.add(q)
    backlog = list(h.events[since:])

    async def gen():
        try:
            last = since - 1
            for e in backlog:
                last = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if e["seq"] <= last:
                    continue
                last = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
        finally:
            h.subscribers.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ResumeBody(BaseModel):
    action: str  # pick | regenerate | approve | request_changes
    id: str | None = None
    notes: str | None = None
    feedback: str | None = None
    preferences: dict | None = None
    candidate_count: int | None = None


@app.post("/runs/{run_id}/resume")
async def resume(run_id: str, body: ResumeBody):
    if body.action == "pick" and not body.id:
        raise HTTPException(422, "pick needs an id")
    try:
        await app.state.runs.resume(run_id, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "run not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.get("/runs/{run_id}/artifacts/{path:path}")
async def artifact(run_id: str, path: str):
    root = (settings.runs_dir() / run_id).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.name == "events.jsonl":
        raise HTTPException(404, "not found")
    headers = {"Cache-Control": "no-store"}
    if target.suffix == ".html":
        # Generated pages are untrusted: an opaque origin even when opened directly.
        headers["Content-Security-Policy"] = "sandbox allow-scripts"
    return FileResponse(target, headers=headers)


@app.get("/runs/{run_id}/download/{kind}")
async def download(run_id: str, kind: str):
    root = settings.runs_dir() / run_id
    files = {"zip": root / "handoff.zip", "html": root / "output" / "index.html", "pdf": root / "output" / "design.pdf",
             "handoff": root / "output" / "HANDOFF.md", "tokens": root / "output" / "tokens.json"}
    f = files.get(kind)
    if not f or not f.exists():
        raise HTTPException(404, "not available")
    names = {"zip": f"ui-agent-{run_id}.zip", "html": "index.html", "pdf": "design.pdf", "handoff": "HANDOFF.md",
             "tokens": "tokens.json"}
    return FileResponse(f, filename=names[kind])


@app.get("/memory")
async def get_memory():
    return await memory.dump_all(app.state.store, USER_ID)


class MemoryUpdate(BaseModel):
    taste: dict | None = None


@app.put("/memory")
async def put_memory(body: MemoryUpdate):
    if body.taste is not None:
        await app.state.store.aput(memory.TASTE_NS(USER_ID), "profile", body.taste)
    return await memory.dump_all(app.state.store, USER_ID)


@app.delete("/memory")
async def delete_memory(what: str = "all"):
    await memory.reset(app.state.store, USER_ID, what)
    return {"ok": True}


@app.get("/memory/last-preferences")
async def last_preferences():
    taste = await memory.get_taste(app.state.store, USER_ID)
    return {"preferences": taste.get("last_preferences"), "candidate_count": taste.get("last_candidate_count")}
