# SPDX-License-Identifier: AGPL-3.0-or-later
"""The model's verdict over the fact-check sources, and the rule that keeps it
honest: **no verdict without sources**, enforced here, not in the prompt.

1. With zero :py:class:`~searx.fork.result_types.ClaimReview` results the
   model is not called at all.
2. The prompt holds only the numbered sources and the user's claim.
3. The reply must match :py:data:`SCHEMA`; an empty or invalid citation list,
   or a verdict more certain than every cited source, or one that flips the
   sources' direction, is discarded and the panel says the summary is
   unavailable (the reason goes to the log).
"""

from __future__ import annotations

__all__ = ["SCHEMA", "build_messages", "validate", "request_verdict"]

import logging
import typing as t

from searx.fork.factcheck.verdict_types import VERDICTS
from searx.fork.llm import LlmError, Message, complete, model_label
from searx.fork.result_types import ClaimReview, LlmVerdictAnswer

logger = logging.getLogger("searx.fork.factcheck.llm")

MAX_SOURCES = 12

SCHEMA: dict[str, t.Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "confidence", "summary", "citations", "caveat"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "summary": {"type": "string", "description": "At most three sentences."},
        "citations": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
        "caveat": {"type": "string", "description": "What the sources do not settle; may be empty."},
    },
}

SYSTEM = (
    "You summarise what professional fact-checkers found about a claim. "
    "Use only the numbered sources given; you have no other knowledge for this task. "
    "Give a verdict from the allowed list, a confidence, a summary of at most three sentences, "
    "the numbers of the sources you relied on, and a caveat if the sources leave something open. "
    "Never be more certain than the sources are. If the sources do not address the claim, say so "
    "in the summary and use the verdict \"unrated\" with at least one citation to the closest source."
)

# how far from "undecided" each verdict is, and in which direction
_STRENGTH: dict[str, tuple[int, int]] = {
    "false": (2, -1),
    "mostly-false": (1, -1),
    "misleading": (1, -1),
    "mixed": (0, 0),
    "unproven": (0, 0),
    "outdated": (0, 0),
    "satire": (1, -1),
    "mostly-true": (1, 1),
    "true": (2, 1),
    "unrated": (0, 0),
}


def _source_line(index: int, review: ClaimReview) -> str:
    parts = [f"[{index}] {review.reviewer or 'unknown reviewer'}"]
    if review.verdict_raw:
        parts.append(f"rating: {review.verdict_raw}")
    else:
        parts.append("rating: not given")
    if review.review_date:
        parts.append(f"date: {review.review_date}")
    if review.claim:
        parts.append(f"reviewed claim: {review.claim}")
    if review.title and review.title != review.claim:
        parts.append(f"title: {review.title}")
    if review.content:
        parts.append(f"note: {review.content[:300]}")
    parts.append(f"url: {review.url}")
    return "\n".join(parts)


def build_messages(claim: str, reviews: list[ClaimReview]) -> list[Message]:
    sources = "\n\n".join(_source_line(i + 1, r) for i, r in enumerate(reviews[:MAX_SOURCES]))
    user = f"Claim to assess:\n{claim}\n\nSources:\n\n{sources}"
    return [Message(role="system", content=SYSTEM), Message(role="user", content=user)]


def _check_shape(data: dict[str, t.Any]) -> str:
    if data.get("verdict") not in VERDICTS:
        return f"unknown verdict {data.get('verdict')!r}"
    if data.get("confidence") not in ("low", "medium", "high"):
        return "missing confidence"
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return "empty summary"
    citations = data.get("citations")
    if not isinstance(citations, list) or not citations:
        return "no citations"
    return ""


def _cited(citations: list[t.Any], reviews: list[ClaimReview]) -> tuple[list[ClaimReview], str]:
    cited: list[ClaimReview] = []
    for index in citations:
        if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= min(len(reviews), MAX_SOURCES):
            return [], f"citation {index!r} is not a source number"
        cited.append(reviews[index - 1])
    return cited, ""


def validate(data: dict[str, t.Any], reviews: list[ClaimReview]) -> str:
    """``""`` when ``data`` is an acceptable verdict over ``reviews``, else the
    reason it is not."""
    problem = _check_shape(data)
    if problem:
        return problem
    cited, problem = _cited(data["citations"], reviews)
    if problem:
        return problem
    verdict = str(data["verdict"])
    strength, direction = _STRENGTH[verdict]
    if not strength:
        return ""
    if strength > max(_STRENGTH[r.verdict][0] for r in cited):
        return f"verdict {verdict} is more certain than every cited source"
    if not any(_STRENGTH[r.verdict][1] == direction for r in cited if _STRENGTH[r.verdict][0]):
        return f"verdict {verdict} points the other way from the cited sources"
    return ""


def request_verdict(claim: str, reviews: list[ClaimReview], *, timeout: float | None = None) -> LlmVerdictAnswer:
    """The panel for ``claim`` over ``reviews``: the model's reading when it
    passes :py:func:`validate`, else an *unavailable* panel.  Never raises."""
    answer = LlmVerdictAnswer(query=claim, model_label=model_label())
    if not reviews:
        answer.reason = "no sources"
        return answer
    try:
        reply = complete(build_messages(claim, reviews), json_schema=SCHEMA, timeout=timeout)
    except LlmError as exc:
        logger.warning("model summary unavailable: %s", exc)
        answer.reason = "the model did not answer"
        return answer
    data = reply.data or {}
    problem = validate(data, reviews)
    if problem:
        logger.warning("model summary discarded: %s (reply: %s)", problem, reply.text[:300])
        answer.reason = "the reply did not pass the source check"
        answer.latency_ms = reply.latency_ms
        return answer
    cited = sorted({int(i) for i in data["citations"]})
    answer.available = True
    answer.verdict = str(data["verdict"])
    answer.confidence = str(data["confidence"])
    answer.summary = " ".join(str(data["summary"]).split())
    answer.caveat = " ".join(str(data.get("caveat") or "").split())
    answer.citations = [
        {
            "index": str(i),
            "reviewer": reviews[i - 1].reviewer,
            "verdict_raw": reviews[i - 1].verdict_raw,
            "url": str(reviews[i - 1].url or ""),
            "title": reviews[i - 1].title,
        }
        for i in cited
    ]
    answer.latency_ms = reply.latency_ms
    return answer
