# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI's API: the ``openai_compat`` wire format at a fixed address, plus the
Responses API's web-search tool for the search assist."""

from __future__ import annotations

import typing as t
from urllib.parse import urlparse

from searx.fork.llm.types import Completion, LlmError, Message, SearchAnswer
from searx.fork.llm.backends import api_key, http_post
from searx.fork.llm.backends.openai_compat import chat

BASE_URL = "https://api.openai.com/v1"


def _require_key() -> str:
    key = api_key()
    if not key:
        raise LlmError("FORK_LLM_API_KEY is not set")
    return key


def complete(
    messages: list[Message],
    *,
    json_schema: dict[str, t.Any] | None,
    images: list[bytes],
    timeout: float,
    model: str,
    max_tokens: int,
) -> Completion:
    _require_key()
    if images:
        raise LlmError("images are not supported by this backend yet")
    return chat(
        BASE_URL + "/chat/completions",
        messages,
        json_schema=json_schema,
        timeout=timeout,
        model=model,
        max_tokens=max_tokens,
    )


def web_search(query: str, *, max_fetches: int, timeout: float, model: str) -> SearchAnswer:
    key = _require_key()
    body: dict[str, t.Any] = {
        "model": model,
        "input": query,
        "instructions": (
            "Answer the question briefly, in at most four sentences, using web search. "
            "Cite the pages you rely on. If the sources disagree or are thin, say so."
        ),
        "tools": [{"type": "web_search_preview"}],
        "max_output_tokens": 600,
    }
    reply = http_post(
        BASE_URL + "/responses",
        body,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        timeout,
    )
    if reply.status != 200:
        raise LlmError(f"HTTP {reply.status} from OpenAI: {str(reply.data)[:200]}")
    data: t.Any = reply.data
    text_parts: list[str] = []
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            text_parts.append(str(part.get("text") or ""))
            for ann in part.get("annotations") or []:
                if isinstance(ann, dict) and ann.get("type") == "url_citation" and ann.get("url"):
                    url = str(ann["url"])
                    if url not in seen and len(citations) < max_fetches:
                        seen.add(url)
                        citations.append({"url": url, "title": str(ann.get("title") or url)})
    fetched = sorted({urlparse(c["url"]).netloc for c in citations if urlparse(c["url"]).netloc})
    return SearchAnswer(
        text="\n".join(p for p in text_parts if p).strip(),
        citations=citations,
        fetched=fetched,
        model=str(data.get("model") or model),
    )
