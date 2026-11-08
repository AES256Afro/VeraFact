# SPDX-License-Identifier: AGPL-3.0-or-later
"""The *Model assist* switch and the frontier search assist.

The switch has three states.  ``off``: no model touches the page.
``summary``: the configured model summarises the fact-check sources (this is
what *Local* means on the switch; a frontier backend does the same).
``answer``: a frontier backend also searches the web itself and writes an
answer above ordinary results.  The state comes from the ``assist`` form field,
is remembered in a cookie for this browser, and otherwise follows the owner's
settings.
"""

from __future__ import annotations

__all__ = ["STATES", "resolve_state", "remember_state", "answer_allowed", "request_answer", "switch_items"]

import logging
import typing as t
from urllib.parse import urlencode

from flask import after_this_request

from searx import get_setting
from searx.fork import llm
from searx.fork.result_types import AssistAnswer

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Request

logger = logging.getLogger("searx.fork.factcheck.assist")

STATES = ("off", "summary", "answer")
FIELD = "assist"
COOKIE = "vf_assist"
COOKIE_MAX_AGE = 365 * 24 * 3600


def answer_allowed() -> bool:
    """Whether the owner lets a model search the web: a frontier backend with
    ``search_assist`` on, or a local backend explicitly marked able to search."""
    if not llm.enabled() or not get_setting("fork.llm.search_assist", False):
        return False
    return llm.is_frontier() or bool(get_setting("fork.llm.search_assist_local", False))


def _default_state() -> str:
    if not llm.enabled():
        return "off"
    if answer_allowed() and get_setting("fork.llm.search_assist_default", False):
        return "answer"
    return "summary"


def resolve_state(request: "SXNG_Request") -> str:
    """The state for this request: the form field, else the browser's cookie,
    else the owner's default.  Clamped to what the settings allow."""
    raw = ""
    try:
        raw = request.form.get(FIELD) or request.args.get(FIELD) or ""
    except Exception:  # pylint: disable=broad-exception-caught
        raw = ""
    explicit = raw.strip().lower() in STATES
    state = raw.strip().lower() if explicit else (request.cookies.get(COOKIE) or "").strip().lower()
    if state not in STATES:
        state = _default_state()
    if not llm.enabled():
        state = "off"
    elif state == "answer" and not answer_allowed():
        state = "summary"
    if explicit:
        remember_state(state)
    return state


def remember_state(state: str) -> None:
    """Keep ``state`` in this browser's cookie for a year."""

    @after_this_request
    def _set(response):  # type: ignore[no-untyped-def]
        response.set_cookie(COOKIE, state, max_age=COOKIE_MAX_AGE, samesite="Lax", httponly=True)
        return response


def switch_items(request: "SXNG_Request", query: str, mode: str) -> list[dict[str, str]]:
    """The entries of the Model assist switch for the templates: label, state,
    link (re-runs the query with that state) and whether it is current."""
    if not llm.enabled():
        return []
    current = resolve_state(request)
    root = (getattr(request, "script_root", "") or "").rstrip("/")

    def link(state: str) -> str:
        args: dict[str, str] = {"q": query, FIELD: state}
        if mode:
            args["mode"] = mode
        return f"{root}/search?{urlencode(args)}"

    items = [
        {"state": "off", "label": "Off"},
        {"state": "summary", "label": "Local" if llm.backend_name() == "openai_compat" else "Frontier"},
    ]
    if answer_allowed():
        items.append({"state": "answer", "label": "Answer"})
    for item in items:
        item["link"] = link(item["state"])
        item["current"] = "1" if item["state"] == current else ""
    return items


def request_answer(query: str, hide_link: str = "") -> AssistAnswer:
    """The frontier model's answer for ``query``, or an *unavailable* panel.
    Never raises."""
    answer = AssistAnswer(query=query, model_label=llm.model_label(), hide_link=hide_link)
    if not answer_allowed():
        answer.reason = "search assist is off"
        return answer
    try:
        reply = llm.web_search(
            query,
            max_fetches=int(get_setting("fork.llm.search_assist_max_fetches", 6)),
            timeout=float(get_setting("fork.llm.search_assist_timeout", 8)),
        )
    except llm.LlmError as exc:
        logger.warning("search assist unavailable: %s", exc)
        answer.reason = "the model did not answer"
        return answer
    if not reply.text.strip() or not reply.citations:
        logger.warning("search assist discarded: no citation (text: %s)", reply.text[:200])
        answer.reason = "the answer cited nothing"
        answer.latency_ms = reply.latency_ms
        return answer
    answer.available = True
    answer.text = reply.text.strip()
    answer.citations = reply.citations
    answer.fetched = reply.fetched
    answer.latency_ms = reply.latency_ms
    return answer
