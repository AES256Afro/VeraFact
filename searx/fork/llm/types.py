# SPDX-License-Identifier: AGPL-3.0-or-later
"""Types shared by the model layer and its backends (kept apart so the two
import in one direction only)."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

__all__ = ["Message", "Completion", "SearchAnswer", "LlmError", "LlmDisabled", "parse_json_object", "FRONTIER_BACKENDS"]

import json
import re
import typing as t

import msgspec

FRONTIER_BACKENDS = ("anthropic", "openai")
"""Backends that may run the search assist."""


class LlmError(Exception):
    """The backend could not produce a reply (network, HTTP, bad output)."""


class LlmDisabled(LlmError):
    """``fork.llm.backend`` is ``disabled``."""


class Message(msgspec.Struct, kw_only=True):
    """One turn of the conversation sent to the model."""

    role: t.Literal["system", "user", "assistant"]
    content: str


class Completion(msgspec.Struct, kw_only=True):
    """What the backend answered."""

    text: str
    """The reply as text (for a schema call, the JSON the model produced)."""
    data: dict[str, t.Any] | None = None
    """The parsed JSON object when a schema was requested."""
    model: str = ""
    backend: str = ""
    latency_ms: int = 0


class SearchAnswer(msgspec.Struct, kw_only=True):
    """A frontier model's answer written with its own web search."""

    text: str
    citations: list[dict[str, str]] = []
    """``{"url": ..., "title": ...}`` for each page the answer cites."""
    fetched: list[str] = []
    """Hosts of the pages the provider fetched, for the panel's disclosure."""
    model: str = ""
    backend: str = ""
    latency_ms: int = 0


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def _object_end(text: str, start: int) -> int:
    """Index just past the ``}`` that closes the object opening at ``start``,
    or ``-1`` when it never closes."""
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def parse_json_object(text: str) -> dict[str, t.Any] | None:
    """The first JSON object in ``text``, tolerant of code fences and prose
    around it; ``None`` when there is none."""
    if not text:
        return None
    candidate = _FENCE.sub("", text.strip())
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    start = candidate.find("{")
    while start != -1:
        end = _object_end(candidate, start)
        if end != -1:
            try:
                data = json.loads(candidate[start:end])
                if isinstance(data, dict):
                    return data
            except ValueError:
                pass
        start = candidate.find("{", start + 1)
    return None
