# SPDX-License-Identifier: AGPL-3.0-or-later
"""Answers written by the model layer: the verdict panel in fact-check mode
and the search assist's answer.  Both always name the model and where it ran."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

__all__ = ["LlmVerdictAnswer", "AssistAnswer"]

from searx.result_types.answer import BaseAnswer


class LlmVerdictAnswer(BaseAnswer, kw_only=True):
    """The model's reading of the fact-check sources, with citations into
    them, or the reason there is none.  Rendered below the no-model summary,
    never instead of the sources."""

    template: str = "answer/fork_llm_verdict.html"
    query: str
    model_label: str = ""
    """*qwen2.5:3b, local* etc., for the header."""
    available: bool = False
    reason: str = ""
    """Why there is no summary (shown as "model summary unavailable"; the detail goes to the log)."""
    verdict: str = "unrated"
    confidence: str = ""
    summary: str = ""
    caveat: str = ""
    citations: list[dict[str, str]] = []
    """``{"index", "reviewer", "verdict_raw", "url", "title"}`` for each cited source."""
    latency_ms: int = 0

    def __hash__(self):
        return hash((self.template, self.query))


class AssistAnswer(BaseAnswer, kw_only=True):
    """A frontier model's answer, written with the provider's own web search,
    above ordinary results.  Dropped without a citation."""

    template: str = "answer/fork_assist.html"
    query: str
    model_label: str = ""
    available: bool = False
    reason: str = ""
    text: str = ""
    citations: list[dict[str, str]] = []
    fetched: list[str] = []
    latency_ms: int = 0
    hide_link: str = ""
    """Relative URL that turns the answer off for this browser."""

    def __hash__(self):
        return hash((self.template, self.query))
