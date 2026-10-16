"""4.7 design_page: turn one page's approved sketch into its first full design (refine v1). The key page (the
entry page of flow 1) comes first and makes every visual decision within the direction; every later page is
designed against the key page's final HTML, and code copies the key page's tokens into it."""

from __future__ import annotations

import json
from typing import Literal

from langgraph.types import Command

from .. import mock, settings
from ..library import style_recipe
from ..llm import get_llm, over_budget
from ..state import AgentState, DirectionBrief, brief_text
from .common import emit, extract_html, key_page_id, lock_tokens, page_links, page_spec, run_dir, shots_dir, with_base_layer
from .render import render_design
from .sketch import page_flows, sketch_notation, site_map


def designer_content(state: AgentState, page: dict, sketch: dict, notes: str, key_html: str | None) -> list:
    lessons = (state.get("memory_context") or {}).get("lessons") or []
    answers = (state.get("kickoff") or {}).get("answers") or []
    direction = state["direction"]
    design_brief = {k: v for k, v in state["intake"].items() if k not in ("questions", "pages")}
    parts = [
        f"<pm_brief>\n{brief_text(state['brief'])}\n</pm_brief>",
        f"<design_brief>\n{json.dumps(design_brief, indent=1)}\n</design_brief>",
    ]
    if answers:
        parts.append(f"<kickoff_answers>\n{json.dumps(answers, indent=1)}\n</kickoff_answers>")
    parts.append(f"<direction>\n{json.dumps(direction, indent=1)}\n</direction>")
    if recipe := style_recipe(direction.get("style_id")):
        parts.append(f"<style_recipe>\n{json.dumps(recipe, indent=1)}\n</style_recipe>")
    parts += [
        f"<site_map>\n{json.dumps(site_map(state['intake']), indent=1)}\n</site_map>",
        f"<this_page>\n{json.dumps(page, indent=1)}\n</this_page>",
        f"<flow_steps_on_this_page>\n{json.dumps(page_flows(state['intake'], page['id']), indent=1)}\n</flow_steps_on_this_page>",
        f"<approved_sketch>\n{sketch.get('text') or '(The sketch for this page failed. Design it from this_page and the flows.)'}</approved_sketch>",
        f"<pm_notes>{notes or '(none)'}</pm_notes>",
    ]
    if key_html:
        parts.append(f"<key_page_html>\nThe site's first page, already designed and reviewed. This page joins it.\n{key_html}\n</key_page_html>")
    if lessons:
        parts.append("<preflight_checklist>\nMistakes earlier designs made repeatedly. Avoid them:\n"
                     + "\n".join(f"- {l['id']}: {l.get('pattern', '')} → {l.get('fix', '')}" for l in lessons)
                     + "\n</preflight_checklist>")
    return [{"type": "text", "text": "\n\n".join(parts)}]


async def design_page(state: AgentState) -> Command[Literal["lock_style", "next_page"]]:
    pid = state["page_id"]
    page = page_spec(state, pid)
    pages = dict(state.get("pages") or {})
    if over_budget(state.get("usage")):
        emit("page_skipped", page_id=pid, reason="budget")
        pages[pid] = {"page_id": pid, "skipped": "budget"}
        return Command(goto="next_page", update={"pages": pages})

    key = key_page_id(state)
    key_done = pages.get(key) or {}
    root = run_dir(state["run_id"])
    key_html = (root / key_done["best"]["html_path"]).read_text() if pid != key and key_done.get("best") else None
    notes = "\n".join(filter(None, [state.get("sketch_notes")] + [c["suggested_fix"] for c in state.get("change_requests") or []]))
    sketch = next((s for s in state.get("sketches") or [] if s["page_id"] == pid), {})
    emit("design_started", page_id=pid, name=page["name"])

    system = settings.prompt("generator").replace("{html_contract}", settings.prompt("html_contract")) \
        .replace("{sketch_notation}", sketch_notation())
    direction = DirectionBrief(**state["direction"])
    text, usage = await get_llm().text(
        "generator", system=system, content=designer_content(state, page, sketch, notes, key_html),
        mock=lambda: mock.html_for(direction, state["intake"], page, notes=notes),
    )
    html = with_base_layer(extract_html(text))
    if key_html:
        html, changed = lock_tokens(html, (state.get("style_lock") or {}).get("tokens") or {})
        if changed:
            emit("tokens_locked", page_id=pid, changed=changed)
    rel_path = f"pages/{pid}/v1.html"
    (root / "pages" / pid).mkdir(parents=True, exist_ok=True)
    (root / rel_path).write_text(html)
    first, _ = await render_design(state["run_id"], {"direction_id": direction.id, "page_id": pid, "version": 1,
                                                     "html_path": rel_path}, shots_dir(rel_path), page_links(state, pid))
    emit("design_ready", page_id=pid, design=first)
    return Command(goto="lock_style", update={"design": first, "usage": usage})
