# SPDX-License-Identifier: AGPL-3.0-or-later
"""Result types the fork adds.  They are plain :py:mod:`searx.result_types`
structs; engines and plugins import them from here."""

__all__ = [
    "ClaimReview",
    "Verdict",
    "VERDICTS",
    "FactCheckOffer",
    "FactCheckSummary",
    "LlmVerdictAnswer",
    "AssistAnswer",
]

from .claim_review import ClaimReview, Verdict, VERDICTS
from .factcheck_answers import FactCheckOffer, FactCheckSummary
from .llm_answers import LlmVerdictAnswer, AssistAnswer
