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
    """POST JSON and return the reply's JSON body (or its text when it is not
    JSON).  Raises :py:class:`~searx.fork.llm.types.LlmError` on transport
    failure.

    A plain ``http://`` address is a local model server (Ollama, LM Studio,
    llama.cpp on this box or the LAN): it is reached directly with the standard
    library, because SearXNG's outgoing network only speaks https unless the
    owner turns ``outgoing.enable_http`` on for every engine.  ``https://``
    addresses go through :py:mod:`searx.network`, so proxies apply.
    """
    if url.lower().startswith("http://"):
        return _post_plain_http(url, body, headers, timeout)
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


def _post_plain_http(url: str, body: dict[str, t.Any], headers: dict[str, str], timeout: float) -> HttpReply:
    import json  # pylint: disable=import-outside-toplevel
    import urllib.error  # pylint: disable=import-outside-toplevel
    import urllib.request  # pylint: disable=import-outside-toplevel

    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # nosec: local model server, owner-configured
            raw = resp.read()
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise LlmError(f"request to {url} failed: {exc.__class__.__name__}: {exc}") from exc
    text = raw.decode("utf-8", errors="replace")
    try:
        data: t.Any = json.loads(text)
    except ValueError:
        data = text
    return HttpReply(status=status, data=data)
