# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-style ``/chat/completions`` servers: Ollama (``:11434/v1``), LM
Studio (``:1234/v1``), llama.cpp server (``:8080/v1``), vLLM.

A JSON schema is first requested with ``response_format: json_schema``; a
server that rejects that gets the schema in the instructions instead and the
reply is parsed strictly.
"""

from __future__ import annotations

import json
import typing as t

from searx import get_setting
from searx.fork.llm.types import Completion, LlmError, Message, parse_json_object
from searx.fork.llm.backends import api_key, http_post

DEFAULT_BASE_URL = ""


def base_url() -> str:
    url = str(get_setting("fork.llm.base_url", "") or DEFAULT_BASE_URL).rstrip("/")
    if not url:
        raise LlmError("fork.llm.base_url is not set (for example http://host.docker.internal:11434/v1)")
    return url


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _messages(messages: list[Message], schema_note: str = "") -> list[dict[str, str]]:
    out = [{"role": m.role, "content": m.content} for m in messages]
    if schema_note:
        if out and out[0]["role"] == "system":
            out[0] = {"role": "system", "content": out[0]["content"] + "\n\n" + schema_note}
        else:
            out.insert(0, {"role": "system", "content": schema_note})
    return out


def chat(
    url: str,
    messages: list[Message],
    *,
    json_schema: dict[str, t.Any] | None,
    timeout: float,
    model: str,
    max_tokens: int,
) -> Completion:
    """Shared by this backend and the ``openai`` one."""
    if not model:
        raise LlmError("fork.llm.model is not set")
    body: dict[str, t.Any] = {
        "model": model,
        "messages": _messages(messages),
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "reply", "schema": json_schema, "strict": True},
        }
    reply = http_post(url, body, _headers(), timeout)

    if reply.status == 400 and json_schema is not None:
        # the server does not know response_format: ask in words and parse strictly
        note = "Reply with a single JSON object and nothing else. It must match this JSON schema:\n" + json.dumps(
            json_schema
        )
        body.pop("response_format")
        body["messages"] = _messages(messages, note)
        reply = http_post(url, body, _headers(), timeout)

    if reply.status != 200:
        raise LlmError(f"HTTP {reply.status} from {url}: {str(reply.data)[:200]}")
    data: t.Any = reply.data
    try:
        text = str(data["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError("unexpected reply shape") from exc
    completion = Completion(text=text, model=str(data.get("model") or model))
    if json_schema is not None:
        completion.data = parse_json_object(text)
    return completion


def complete(
    messages: list[Message],
    *,
    json_schema: dict[str, t.Any] | None,
    images: list[bytes],
    timeout: float,
    model: str,
    max_tokens: int,
) -> Completion:
    if images:
        raise LlmError("images are not supported by this backend yet")
    return chat(
        base_url() + "/chat/completions",
        messages,
        json_schema=json_schema,
        timeout=timeout,
        model=model,
        max_tokens=max_tokens,
    )
