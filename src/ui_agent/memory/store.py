"""Long-term memory on the LangGraph Store (plan §9).

Write policy: only explicit signals (sketch picks, notes, recurring
issues). Raw transcripts are never stored. A lesson is promoted only after it has
shown up in at least LESSON_PROMOTION_RUNS different runs."""

from __future__ import annotations

import time

from langgraph.store.base import BaseStore

LESSON_PROMOTION_RUNS = 3

TASTE_NS = lambda uid: ("user", uid, "taste")  # noqa: E731
BRAND_NS = lambda pid: ("project", pid, "brand")  # noqa: E731
LESSONS_NS = ("system", "lessons")
RUNS_NS = lambda uid: ("runs", uid)  # noqa: E731


def _brief_attributes(brief: dict) -> list[str]:
    return [
        f"style:{brief.get('reference_style')}",
        f"layout:{brief.get('layout_id') or brief.get('layout_archetype', '')[:40]}",
        f"font:{brief.get('heading_font')}",
        f"density:{brief.get('density')}",
        f"shape:{brief.get('shape')}",
    ]


async def get_taste(store: BaseStore, uid: str) -> dict:
    item = await store.aget(TASTE_NS(uid), "profile")
    return item.value if item else {"counts": {}, "notes": []}


async def record_pick(store: BaseStore, uid: str, chosen: dict, rejected: list[dict], notes: str) -> None:
    taste = await get_taste(store, uid)
    for attr in _brief_attributes(chosen):
        taste["counts"].setdefault(attr, {"picked": 0, "rejected": 0})["picked"] += 1
    for b in rejected:
        for attr in _brief_attributes(b):
            taste["counts"].setdefault(attr, {"picked": 0, "rejected": 0})["rejected"] += 1
    if notes:
        taste["notes"] = (taste.get("notes", []) + [notes])[-10:]
    await store.aput(TASTE_NS(uid), "profile", taste)


def taste_summary(taste: dict) -> dict:
    scored = sorted(
        ((k, v.get("picked", 0) - 0.5 * v.get("rejected", 0)) for k, v in taste.get("counts", {}).items()),
        key=lambda kv: kv[1], reverse=True,
    )
    return {
        "preferred": [k for k, s in scored if s > 0][:8],
        "avoided": [k for k, s in scored if s < 0][-5:],
        "notes": taste.get("notes", [])[-5:],
        "has_signal": any(s > 0 for _, s in scored),
    }


async def record_lessons(store: BaseStore, run_id: str, issues: list[dict]) -> None:
    seen = set()
    for iss in issues:
        key = iss["id"]
        if key in seen or key.startswith("chg_"):
            continue
        seen.add(key)
        item = await store.aget(LESSONS_NS, key)
        v = item.value if item else {"pattern": iss.get("evidence", ""), "fix": iss.get("suggested_fix", ""),
                                      "criterion": iss.get("criterion"), "runs": []}
        if run_id not in v["runs"]:
            v["runs"] = (v["runs"] + [run_id])[-20:]
        v["count"] = len(v["runs"])
        v["promoted"] = v["count"] >= LESSON_PROMOTION_RUNS
        await store.aput(LESSONS_NS, key, v)


async def promoted_lessons(store: BaseStore) -> list[dict]:
    items = await store.asearch(LESSONS_NS, limit=200)
    return [{"id": i.key, **i.value} for i in items if i.value.get("promoted")]


async def record_run(store: BaseStore, uid: str, run_id: str, summary: dict) -> None:
    await store.aput(RUNS_NS(uid), run_id, {**summary, "finished_at": time.time()})


async def load_context(store: BaseStore, uid: str, project_id: str | None = None) -> dict:
    taste = await get_taste(store, uid)
    brand = None
    if project_id:
        item = await store.aget(BRAND_NS(project_id), "brand")
        brand = item.value if item else None
    return {"taste": taste_summary(taste), "lessons": await promoted_lessons(store), "brand": brand}


async def dump_all(store: BaseStore, uid: str) -> dict:
    lessons = await store.asearch(LESSONS_NS, limit=200)
    runs = await store.asearch(RUNS_NS(uid), limit=50)
    return {
        "taste": await get_taste(store, uid),
        "lessons": [{"id": i.key, **i.value} for i in lessons],
        "runs": [{"id": i.key, **i.value} for i in runs],
    }


async def reset(store: BaseStore, uid: str, what: str = "all") -> None:
    if what in ("all", "taste"):
        await store.adelete(TASTE_NS(uid), "profile")
    if what in ("all", "lessons"):
        for i in await store.asearch(LESSONS_NS, limit=500):
            await store.adelete(LESSONS_NS, i.key)
    if what in ("all", "runs"):
        for i in await store.asearch(RUNS_NS(uid), limit=500):
            await store.adelete(RUNS_NS(uid), i.key)
