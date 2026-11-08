# SPDX-License-Identifier: AGPL-3.0-or-later
"""Anthropic's Messages API.  A JSON schema becomes a forced tool call, so the
reply is the tool's input; the search assist uses the provider's server-side
web-search tool."""

from __future__ import annotations

import json
import typing as t
from urllib.parse import urlparse

from searx.fork.llm.types import Completion, LlmError, Message, SearchAnswer
from searx.fork.llm.backends import api_key, http_post

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"


def _headers() -> dict[str, str]:
    key = api_key()
    if not key:
        raise LlmError("FORK_LLM_API_KEY is not set")
    return {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": API_VERSION}


def _split(messages: list[Message]) -> tuple[str, list[dict[str, str]]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    if not turns:
        raise LlmError("no user message")
    return system, turns


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
    system, turns = _split(messages)
    body: dict[str, t.Any] = {"model": model or DEFAULT_MODEL, "max_tokens": max_tokens, "messages": turns}
    if system:
        body["system"] = system
    if json_schema is not None:
        body["tools"] = [{"name": "reply", "description": "The structured reply.", "input_schema": json_schema}]
        body["tool_choice"] = {"type": "tool", "name": "reply"}

    reply = http_post(API_URL, body, _headers(), timeout)
    if reply.status != 200:
        raise LlmError(f"HTTP {reply.status} from Anthropic: {str(reply.data)[:200]}")
    data: t.Any = reply.data
    blocks = data.get("content") or []
    if json_schema is not None:
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                return Completion(
                    text=json.dumps(block["input"]), data=block["input"], model=str(data.get("model") or model)
                )
        raise LlmError("the model did not use the reply tool")
    text = "".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    return Completion(text=text, model=str(data.get("model") or model))


def web_search(query: str, *, max_fetches: int, timeout: float, model: str) -> SearchAnswer:
    body: dict[str, t.Any] = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": 700,
        "system": (
            "Answer the question briefly, in at most four sentences, using web search. "
            "Cite the pages you rely on. If the sources disagree or are thin, say so."
        ),
        "messages": [{"role": "user", "content": query}],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": max(1, int(max_fetches))}],
    }
    reply = http_post(API_URL, body, _headers(), timeout)
    if reply.status != 200:
        raise LlmError(f"HTTP {reply.status} from Anthropic: {str(reply.data)[:200]}")
    data: t.Any = reply.data
    text_parts: list[str] = []
    citations: list[dict[str, str]] = []
    fetched: set[str] = set()
    seen: set[str] = set()
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text_parts.append(str(block.get("text") or ""))
            for cit in block.get("citations") or []:
                url = str(cit.get("url") or "") if isinstance(cit, dict) else ""
                if url and url not in seen:
                    seen.add(url)
                    citations.append({"url": url, "title": str(cit.get("title") or url)})
        elif kind == "web_search_tool_result":
            for res in block.get("content") or []:
                if isinstance(res, dict) and res.get("url"):
                    host = urlparse(str(res["url"])).netloc
                    if host:
                        fetched.add(host)
    for c in citations:
        host = urlparse(c["url"]).netloc
        if host:
            fetched.add(host)
    return SearchAnswer(
        text="".join(text_parts).strip(),
        citations=citations,
        fetched=sorted(fetched),
        model=str(data.get("model") or model),
    )
