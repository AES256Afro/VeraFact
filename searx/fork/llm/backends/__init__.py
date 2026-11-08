# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backend modules.  Each exposes ``complete(messages, *, json_schema, images,
timeout, model, max_tokens) -> Completion``; the frontier ones also expose
``web_search(query, *, max_fetches, timeout, model) -> SearchAnswer``."""

from __future__ import annotations

__all__ = ["api_key", "http_post", "HttpReply"]

# pylint: disable=too-few-public-methods

import os
import typing as t

import msgspec

from searx import get_setting
from searx.fork.llm.types import LlmError


class HttpReply(msgspec.Struct, kw_only=True):
    """Status and decoded body of one HTTP reply."""

    status: int
    data: t.Any


def api_key() -> str:
    """``fork.llm.api_key`` (which the environment variable ``FORK_LLM_API_KEY``
    overrides at load time)."""
    return str(get_setting("fork.llm.api_key", "") or os.environ.get("FORK_LLM_API_KEY", "") or "")


def http_post(url: str, body: dict[str, t.Any], headers: dict[str, str], timeout: float) -> HttpReply:
    """POST JSON through :py:mod:`searx.network`; the reply's JSON body, or its
    text when it is not JSON.  Raises :py:class:`searx.fork.llm.LlmError` on
    transport failure."""
    from searx.network import post  # pylint: disable=import-outside-toplevel

    try:
        resp = post(url, json=body, headers=headers, timeout=timeout, raise_for_httperror=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise LlmError(f"request to {url} failed: {exc.__class__.__name__}: {exc}") from exc
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    return HttpReply(status=int(resp.status_code), data=data)
