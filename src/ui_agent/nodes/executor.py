"""4.8 execute: targeted str_replace edits for the top open issues."""

from __future__ import annotations

import json
import shutil

from .. import mock, settings
from ..llm import LLMError, get_llm
from ..tools.text_editor import TextEditor
from ..state import AgentState
from .common import SEVERITY_ORDER, emit, run_dir


def top_issues(issues: list[dict], k: int) -> list[dict]:
    open_ = [i for i in issues if i["status"] in ("open", "regressed")]
    # Change requests from the developer first, then by severity.
    return sorted(open_, key=lambda i: (not i["id"].startswith("chg_"), SEVERITY_ORDER.get(i["severity"], 3)))[:k]


async def apply_fixes(run_id: str, src_rel: str, dst_rel: str, issues: list[dict], *, style_spec: dict | None,
                      do_not_regress: list[dict], regression_note: str | None = None) -> tuple[str, dict, int]:
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
        "Start by viewing the parts of index.html you need.",
    ]))
    system = settings.prompt("executor").replace("{html_contract}", settings.prompt("html_contract"))
    summary, usage = await get_llm().edit_file(
        "executor", system=system, content=content, editor=editor,
        mock=lambda: mock.execute(editor, dst.read_text(), issues),
    )
    return summary or "\n".join(editor.log), usage, editor.edits


async def execute(state: AgentState) -> dict:
    cur = state["current"]
    cfg = settings.config()["refine"]
    issues = top_issues(state.get("issues") or [], int(cfg["top_issues"]))
    resolved = [{"id": i["id"], "evidence": i["evidence"]} for i in (state.get("issues") or []) if i["status"] == "resolved"]
    version = max([cur["version"]] + [h["version"] for h in state.get("history") or []]) + 1
    dst_rel = f"refine/v{version}.html"
    emit("execute_started", version=version, issues=[i["id"] for i in issues])
    try:
        summary, usage, edits = await apply_fixes(
            state["run_id"], cur["html_path"], dst_rel, issues, style_spec=state.get("style_lock"),
            do_not_regress=resolved, regression_note=state.get("regression_note"),
        )
    except LLMError as e:
        emit("execute_failed", version=version, error=str(e))
        return {"stop_reason": f"executor_error: {e}", "gate_decision": "stop"}
    new = {"direction_id": cur["direction_id"], "version": version, "html_path": dst_rel,
           "executor_summary": summary, "addressed": [i["id"] for i in issues]}
    emit("execute_done", version=version, summary=summary, edits=edits)
    return {"current": new, "regression_note": None, "usage": usage, "change_requests_pending": False}
