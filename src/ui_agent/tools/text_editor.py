"""Sandboxed handler for the Anthropic text-editor tool (plan §4.8 `execute`).

The model always edits a virtual file named `index.html`; we map it onto one real
file inside the run directory and refuse every other path."""

from __future__ import annotations

from pathlib import Path

ALLOWED_NAMES = {"index.html", "/index.html", "./index.html"}


class TextEditor:
    def __init__(self, target: Path):
        self.target = target.resolve()
        self.edits = 0
        self.log: list[str] = []

    def _check_path(self, path: str | None) -> str | None:
        if path not in ALLOWED_NAMES:
            return f"Error: only index.html can be viewed or edited (got {path!r})."
        return None

    def handle(self, tool_input: dict) -> tuple[bool, str]:
        cmd = tool_input.get("command")
        err = self._check_path(tool_input.get("path"))
        if err:
            return False, err
        text = self.target.read_text()

        if cmd == "view":
            lines = text.splitlines()
            rng = tool_input.get("view_range")
            start, end = 1, len(lines)
            if rng and len(rng) == 2:
                start = max(1, int(rng[0]))
                end = len(lines) if int(rng[1]) == -1 else min(len(lines), int(rng[1]))
            return True, "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))

        if cmd == "str_replace":
            old, new = tool_input.get("old_str", ""), tool_input.get("new_str", "")
            count = text.count(old) if old else 0
            if count == 0:
                return False, "Error: old_str not found. View the file and copy the exact text, including whitespace."
            if count > 1:
                return False, f"Error: old_str matches {count} places; include more surrounding context so it is unique."
            self.target.write_text(text.replace(old, new, 1))
            self.edits += 1
            self.log.append(f"str_replace: {old[:60]!r} → {new[:60]!r}")
            return True, "Edited successfully."

        if cmd == "insert":
            line = int(tool_input.get("insert_line", 0))
            lines = text.splitlines(keepends=True)
            if not 0 <= line <= len(lines):
                return False, f"Error: insert_line must be between 0 and {len(lines)}."
            ins = tool_input.get("insert_text", "")
            if not ins.endswith("\n"):
                ins += "\n"
            lines.insert(line, ins)
            self.target.write_text("".join(lines))
            self.edits += 1
            self.log.append(f"insert after line {line}")
            return True, "Inserted successfully."

        if cmd == "create":
            return False, "Error: full rewrites are not allowed. Use str_replace for targeted edits."

        return False, f"Error: unsupported command {cmd!r}."
