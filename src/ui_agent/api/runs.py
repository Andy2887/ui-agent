"""Run manager: drives graph runs as background tasks and fans events out to SSE clients.

Every event is appended to runs/<id>/events.jsonl, so a reconnecting (or reloaded)
frontend replays the full history before receiving live events."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field

from langgraph.types import Command

from ..nodes.common import run_dir
from .. import settings

log = logging.getLogger("ui_agent.runs")

# interrupt kind -> run status while it waits for the PM
WAITING = {"kickoff": "waiting_kickoff", "gallery": "waiting_gallery", "final_approval": "waiting_approval"}


@dataclass
class RunHandle:
    run_id: str
    status: str = "running"  # running | waiting_kickoff | waiting_gallery | waiting_approval | done | error
    task: asyncio.Task | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    events: list[dict] = field(default_factory=list)


class RunManager:
    def __init__(self, graph):
        self.graph = graph
        self.runs: dict[str, RunHandle] = {}

    # ------------------------------------------------------------------ events
    def _load(self, run_id: str) -> RunHandle | None:
        if run_id in self.runs:
            return self.runs[run_id]
        path = settings.runs_dir() / run_id / "events.jsonl"
        if not path.exists():
            return None
        events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        status = next((e["status"] for e in reversed(events) if e["type"] == "status"), "error")
        if status == "running":
            status = "error"  # the server restarted mid-run
        h = RunHandle(run_id, status=status, events=events)
        self.runs[run_id] = h
        return h

    def get(self, run_id: str) -> RunHandle | None:
        return self._load(run_id)

    def publish(self, h: RunHandle, event: dict) -> None:
        event = {"seq": len(h.events), "ts": event.get("ts", time.time()), **event}
        h.events.append(event)
        with (run_dir(h.run_id) / "events.jsonl").open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")
        for q in list(h.subscribers):
            q.put_nowait(event)

    def set_status(self, h: RunHandle, status: str, **extra) -> None:
        h.status = status
        self.publish(h, {"type": "status", "status": status, **extra})

    # -------------------------------------------------------------------- runs
    async def start(self, request: dict, user_id: str = "local") -> str:
        run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        root = run_dir(run_id)
        (root / "request.json").write_text(json.dumps(request, indent=2))
        h = RunHandle(run_id)
        self.runs[run_id] = h
        self.set_status(h, "running", request=request, mock=settings.mock_mode())
        initial = {
            "run_id": run_id, "user_id": user_id, "brief": request["brief"],
            "candidate_count": request["candidate_count"], "usage": {},
        }
        h.task = asyncio.create_task(self._drive(h, initial))
        return run_id

    async def resume(self, run_id: str, answer: dict) -> None:
        h = self.get(run_id)
        if h is None:
            raise KeyError(run_id)
        if h.status not in WAITING.values():
            raise ValueError(f"run is {h.status}, not waiting for input")
        self.publish(h, {"type": "resume", "answer": answer})
        self.set_status(h, "running")
        h.task = asyncio.create_task(self._drive(h, Command(resume=answer)))

    async def _drive(self, h: RunHandle, inp) -> None:
        cfg = {"configurable": {"thread_id": h.run_id}, "recursion_limit": 200}
        interrupted = None
        try:
            async for item in self.graph.astream(inp, cfg, stream_mode=["custom", "updates"], subgraphs=True):
                _ns, mode, chunk = item
                if mode == "custom":
                    self.publish(h, chunk)
                elif mode == "updates" and "__interrupt__" in chunk:
                    interrupted = chunk["__interrupt__"][0].value
                elif mode == "updates":
                    for node, upd in chunk.items():
                        if node != "__interrupt__":
                            self.publish(h, {"type": "node_done", "node": node,
                                             "usage": (upd or {}).get("usage") if isinstance(upd, dict) else None})
            if interrupted:
                self.publish(h, {"type": "interrupt", "kind": interrupted["kind"], "payload": interrupted})
                self.set_status(h, WAITING[interrupted["kind"]])
            else:
                state = (await self.graph.aget_state(cfg)).values
                self.set_status(h, "done", stop_reason=state.get("stop_reason"),
                                score=(state.get("best") or {}).get("score"), usage=state.get("usage"))
        except Exception as e:  # surface every failure to the UI
            log.exception("run %s failed", h.run_id)
            self.set_status(h, "error", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])

    def list(self) -> list[dict]:
        out = []
        for p in sorted(settings.runs_dir().glob("*/request.json"), reverse=True)[:50]:
            rid = p.parent.name
            h = self.get(rid)
            req = json.loads(p.read_text())
            brief = req.get("brief") or {}
            title = " · ".join(filter(None, [brief.get("product_name"), brief.get("problem")])) or req.get("prompt", "")
            out.append({"run_id": rid, "prompt": title[:140], "status": h.status if h else "unknown"})
        return out
