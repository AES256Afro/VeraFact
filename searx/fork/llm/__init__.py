# SPDX-License-Identifier: AGPL-3.0-or-later
"""The model layer: one call, four backends, off by default.

:py:func:`complete` sends a short conversation to the configured backend and
returns its reply, optionally constrained to a JSON schema.  It is used only
where ``docs/fork/FEATURES.md`` §3 allows: to summarise fact-check sources that
already exist, and (frontier backends only) for the search assist.  Nothing
here runs on an ordinary search by itself.

Backends (``fork.llm.backend``):

- ``disabled``: :py:func:`complete` raises :py:class:`LlmDisabled`; callers skip the feature.
- ``openai_compat``: any OpenAI-style ``/chat/completions`` server (Ollama's ``/v1``, LM Studio, llama.cpp, vLLM).
- ``openai``: the same wire format at ``https://api.openai.com/v1``.
- ``anthropic``: the Messages API, with tool use for JSON schemas and the provider's web-search tool for the assist.

All HTTP goes through :py:mod:`searx.network`, so outgoing proxies apply.
"""

from __future__ import annotations

__all__ = [
    "Message",
    "Completion",
    "SearchAnswer",
    "LlmDisabled",
    "LlmError",
    "complete",
    "web_search",
    "enabled",
    "backend_name",
    "model_name",
    "model_label",
    "is_frontier",
    "ping",
    "parse_json_object",
]

import time
import typing as t
from collections.abc import Sequence

from searx import get_setting
from searx.fork.llm.types import (
    FRONTIER_BACKENDS,
    Completion,
    LlmDisabled,
    LlmError,
    Message,
    SearchAnswer,
    parse_json_object,
)


def _cfg(name: str, default: t.Any = None) -> t.Any:
    return get_setting(f"fork.llm.{name}", default)


def backend_name() -> str:
    return str(_cfg("backend", "disabled") or "disabled")


def enabled() -> bool:
    return backend_name() != "disabled"


def is_frontier() -> bool:
    return backend_name() in FRONTIER_BACKENDS


def model_name() -> str:
    name = str(_cfg("model", "") or "")
    if not name and backend_name() == "anthropic":
        name = "claude-haiku-5-5"
    if not name and backend_name() == "openai":
        name = "gpt-5-mini"
    return name


def model_label() -> str:
    """For panel headers: *qwen2.5:3b, local* or *claude-haiku-5-5, Anthropic*."""
    backend = backend_name()
    where = {"openai_compat": "local", "anthropic": "Anthropic", "openai": "OpenAI"}.get(backend, backend)
    return f"{model_name() or '?'}, {where}"


def _backend_module() -> t.Any:
    # pylint: disable=import-outside-toplevel
    backend = backend_name()
    if backend == "disabled":
        raise LlmDisabled("fork.llm.backend is disabled")
    if backend == "openai_compat":
        from searx.fork.llm.backends import openai_compat as mod
    elif backend == "openai":
        from searx.fork.llm.backends import openai as mod
    elif backend == "anthropic":
        from searx.fork.llm.backends import anthropic as mod
    else:
        raise LlmError(f"unknown backend {backend!r}")
    return mod


def complete(
    messages: Sequence[Message],
    *,
    json_schema: dict[str, t.Any] | None = None,
    images: Sequence[bytes] = (),
    timeout: float | None = None,
) -> Completion:
    """Send ``messages`` and return the reply.  With ``json_schema`` the reply
    is a JSON object matching it (``Completion.data``), or :py:class:`LlmError`.
    ``images`` are reserved for the OCR backend and are refused unless
    ``fork.llm.allow_images`` is on."""
    if images and not _cfg("allow_images", False):
        raise LlmError("fork.llm.allow_images is off")
    mod = _backend_module()
    started = time.monotonic()
    completion: Completion = mod.complete(
        list(messages),
        json_schema=json_schema,
        images=list(images),
        timeout=float(timeout or _cfg("timeout", 20)),
        model=model_name(),
        max_tokens=int(_cfg("max_tokens", 400)),
    )
    completion.latency_ms = int((time.monotonic() - started) * 1000)
    completion.backend = backend_name()
    completion.model = completion.model or model_name()
    if json_schema is not None and completion.data is None:
        completion.data = parse_json_object(completion.text)
        if completion.data is None:
            raise LlmError("the model did not reply with a JSON object")
    return completion


def web_search(query: str, *, max_fetches: int, timeout: float) -> SearchAnswer:
    """Frontier backends only: let the provider search the web and answer with
    citations.  :py:class:`LlmError` for the local backend."""
    mod = _backend_module()
    if not hasattr(mod, "web_search"):
        raise LlmError(f"backend {backend_name()!r} has no web search")
    started = time.monotonic()
    answer: SearchAnswer = mod.web_search(query, max_fetches=max_fetches, timeout=timeout, model=model_name())
    answer.latency_ms = int((time.monotonic() - started) * 1000)
    answer.backend = backend_name()
    answer.model = answer.model or model_name()
    return answer


def ping(timeout: float = 10.0) -> dict[str, t.Any]:
    """One short prompt, for the preferences page's *Test* button."""
    info: dict[str, t.Any] = {"backend": backend_name(), "model": model_name(), "ok": False}
    try:
        reply = complete([Message(role="user", content="Reply with the single word: ready")], timeout=timeout)
        info.update(ok=True, latency_ms=reply.latency_ms, reply=reply.text.strip()[:80])
    except LlmError as exc:
        info["error"] = str(exc)
    return info
