"""4.8 execute: targeted str_replace edits for the top open issues."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..tools.text_editor import TextEditor
from ..state import AgentState
from .common import SEVERITY_ORDER, emit, key_page_id, lock_tokens, run_dir, with_base_layer


def top_issues(issues: list[dict], k: int) -> list[dict]:
    open_ = [i for i in issues if i["status"] in ("open", "regressed")]
    # Change requests from the PM first, then by severity.
    return sorted(open_, key=lambda i: (not i["id"].startswith("chg_"), SEVERITY_ORDER.get(i["severity"], 3)))[:k]


async def apply_fixes(run_id: str, src_rel: str, dst_rel: str, issues: list[dict], *, style_spec: dict | None,
                      do_not_regress: list[dict], regression_note: str | None = None,
                      locked_tokens: dict | None = None) -> tuple[str, dict, dict]:
    """`locked_tokens`: the key page's tokens, for every other page of the site. Edits can't change them."""
    root = run_dir(run_id)
    dst = root / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / src_rel, dst)
    editor = TextEditor(dst)
    content = "\n\n".join(filter(None, [
        "Fix these issues in index.html (highest priority first):\n" + json.dumps(issues, indent=1),
        "StyleSpec (keep this character):\n" + json.dumps(style_spec, indent=1) if style_spec else None,
        "Do not regress (already fixed):\n" + json.dumps(do_not_regress, indent=1) if do_not_regress else None,
        f"Warning: your previous round made things worse and was reverted. {regression_note}" if regression_note else None,
        "This page belongs to a multi-page site. Its :root token values, site header and footer are shared with the "
        "other pages: leave them unchanged and fix issues in this page's own component CSS and markup." if locked_tokens else None,
        # The whole file up front (about 8k tokens, cached with the rest of the turn) saves the view round trips.
        f"<index_html>\n{dst.read_text()}\n</index_html>",
    ]))
    system = settings.prompt("executor").replace("{html_contract}", settings.prompt("html_contract"))
    summary, usage = await get_llm().edit_file(
        "executor", system=system, content=content, editor=editor,
        mock=lambda: mock.execute(editor, dst.read_text(), issues),
    )
    dst.write_text(with_base_layer(dst.read_text()))  # undo any edit to the base layer
    if locked_tokens:
        dst.write_text(lock_tokens(dst.read_text(), locked_tokens)[0])  # and any edit to the shared tokens
    stats = {"edits": editor.edits, "views": editor.views, "failed_edits": editor.failures, "turns": usage.get("calls", 0),
             "edit_errors": editor.errors[:5]}
    return summary or "\n".join(editor.log), usage, stats


async def execute(state: AgentState) -> dict:
    cur = state["current"]
    cfg = settings.config()["refine"]
    issues = top_issues(state.get("issues") or [], int(cfg["top_issues"]))
    resolved = [{"id": i["id"], "evidence": i["evidence"]} for i in (state.get("issues") or []) if i["status"] == "resolved"]
    page_id = cur.get("page_id")
    version = max([cur["version"]] + [h["version"] for h in state.get("history") or [] if h.get("page_id") == page_id]) + 1
    dst_rel = f"{Path(cur['html_path']).parent}/v{version}.html"
    locked = None
    if page_id and page_id != key_page_id(state):
        locked = (state.get("style_lock") or {}).get("tokens")
    emit("execute_started", page_id=page_id, version=version, issues=[i["id"] for i in issues])
    try:
        summary, usage, stats = await apply_fixes(
            state["run_id"], cur["html_path"], dst_rel, issues, style_spec=state.get("style_lock"),
            do_not_regress=resolved, regression_note=state.get("regression_note"), locked_tokens=locked,
        )
    except LLMError as e:
        emit("execute_failed", page_id=page_id, version=version, error=str(e))
        return {"stop_reason": f"executor_error: {e}", "gate_decision": "stop"}
    new = {"direction_id": cur["direction_id"], "page_id": page_id, "version": version, "html_path": dst_rel,
           "executor_summary": summary, "addressed": [i["id"] for i in issues]}
    emit("execute_done", page_id=page_id, version=version, summary=summary, **stats)
    return {"current": new, "regression_note": None, "usage": usage, "change_requests_pending": False}
