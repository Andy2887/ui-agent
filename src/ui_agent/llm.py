"""The one wrapper that owns every Claude call (plan §10).

- Structured outputs via `output_format=<PydanticModel>` on the streaming helper.
- Adaptive thinking with an explicit per-role `effort`.
- Streaming for everything (long outputs; avoids HTTP timeouts).
- Prompt caching on the stable system prefix (system prompt + contract + rubric).
- Refusals: `stop_reason` is checked before content is read; server-side
  `fallbacks: "default"` is enabled when config.yaml says so.
- Usage per call is returned so nodes can add it to `state.usage`.
- In mock mode (UI_AGENT_MOCK=1) every call returns the supplied offline stand-in.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

import anthropic
from pydantic import BaseModel

from . import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
TEXT_EDITOR_TOOL = {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


@dataclass
class RoleConfig:
    model: str
    effort: str
    max_tokens: int


def role_config(role: str) -> RoleConfig:
    c = settings.config()["models"][role]
    return RoleConfig(model=c["model"], effort=c["effort"], max_tokens=int(c["max_tokens"]))


def cost_usd(model: str, usage: dict) -> float:
    prices = settings.config()["pricing"].get(model) or settings.config()["pricing"]["claude-sonnet-5-5"]
    return (
        usage.get("input_tokens", 0) * prices["input"]
        + usage.get("output_tokens", 0) * prices["output"]
        + usage.get("cache_read_input_tokens", 0) * prices["cache_read"]
        + usage.get("cache_creation_input_tokens", 0) * prices["cache_write"]
    ) / 1_000_000


def over_budget(usage: dict | None) -> bool:
    return (usage or {}).get("cost_usd", 0.0) >= float(settings.config()["budget_usd_per_run"])


def _usage_of(role: str, msg: Any) -> dict:
    u = msg.usage
    d = {
        "input_tokens": u.input_tokens or 0,
        "output_tokens": u.output_tokens or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    d["cost_usd"] = cost_usd(getattr(msg, "model", "") or role_config(role).model, d)
    out = {f"{role}.{k}": v for k, v in d.items()}
    out.update(d)  # run totals
    out["calls"] = 1
    return out


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


async def _maybe_await(v):
    return await v if inspect.isawaitable(v) else v


class LLM:
    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(max_retries=4)
        return self._client

    def _base_kwargs(self, role: str, system: str, messages: list) -> dict:
        rc = role_config(role)
        kwargs: dict[str, Any] = {
            "model": rc.model,
            "max_tokens": rc.max_tokens,
            # Stable prefix first, cached; volatile content (HTML, screenshots) goes in messages.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": rc.effort},
        }
        if settings.config().get("fallbacks"):
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = settings.config()["fallbacks"]
        return kwargs

    async def _stream(self, role: str, **kwargs) -> Any:
        try:
            async with self.client.beta.messages.stream(**kwargs) as stream:
                msg = await stream.get_final_message()
        except anthropic.APIStatusError as e:
            raise LLMError(f"{role}: Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"{role}: could not reach the Claude API: {e}") from e
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            raise LLMRefusal(f"{role}: request declined ({getattr(details, 'category', None)})")
        if msg.stop_reason == "max_tokens":
            raise LLMError(f"{role}: output hit max_tokens ({kwargs['max_tokens']})")
        return msg

    # ------------------------------------------------------------------ parse
    async def parse(
        self,
        role: str,
        *,
        system: str,
        content: list | str,
        output_format: type[T],
        mock: Callable[[], T | Awaitable[T]],
    ) -> tuple[T, dict]:
        if settings.mock_mode():
            return await _maybe_await(mock()), {"calls": 1}
        kwargs = self._base_kwargs(role, system, [{"role": "user", "content": content}])
        msg = await self._stream(role, output_format=output_format, **kwargs)
        parsed = getattr(msg, "parsed_output", None)
        if parsed is None:
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            parsed = output_format.model_validate_json(text)
        return parsed, _usage_of(role, msg)

    # ------------------------------------------------------------------- text
    async def text(
        self,
        role: str,
        *,
        system: str,
        content: list | str,
        mock: Callable[[], str | Awaitable[str]],
    ) -> tuple[str, dict]:
        if settings.mock_mode():
            return await _maybe_await(mock()), {"calls": 1}
        kwargs = self._base_kwargs(role, system, [{"role": "user", "content": content}])
        msg = await self._stream(role, **kwargs)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text, _usage_of(role, msg)

    # -------------------------------------------------------------- edit loop
    async def edit_file(
        self,
        role: str,
        *,
        system: str,
        content: list | str,
        editor: "TextEditorLike",
        mock: Callable[[], str | Awaitable[str]],
        max_tool_calls: int | None = None,
    ) -> tuple[str, dict]:
        """Agentic loop with the Anthropic text-editor tool; edits are applied by `editor`."""
        if settings.mock_mode():
            return await _maybe_await(mock()), {"calls": 1}
        max_tool_calls = max_tool_calls or int(settings.config()["executor_max_tool_calls"])
        messages: list = [{"role": "user", "content": content}]
        usage: dict = {}
        calls = 0
        final_text = ""
        while True:
            kwargs = self._base_kwargs(role, system, messages)
            kwargs["tools"] = [TEXT_EDITOR_TOOL]
            kwargs["cache_control"] = {"type": "ephemeral"}  # also cache the growing history
            msg = await self._stream(role, **kwargs)
            usage = _merge(usage, _usage_of(role, msg))
            messages.append({"role": "assistant", "content": msg.content})  # append-only history
            final_text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text") or final_text
            tool_uses = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
            if msg.stop_reason != "tool_use" or not tool_uses:
                break
            results = []
            for block in tool_uses:
                calls += 1
                if calls > max_tool_calls:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": "Edit budget exhausted. Stop editing and summarize what you changed."})
                    continue
                ok, out = editor.handle(json.loads(json.dumps(block.input)))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out, "is_error": not ok})
            messages.append({"role": "user", "content": results})
            if calls > max_tool_calls + 3:
                break
        return final_text, usage


class TextEditorLike:  # protocol
    def handle(self, tool_input: dict) -> tuple[bool, str]: ...


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
