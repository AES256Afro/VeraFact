# SPDX-License-Identifier: AGPL-3.0-or-later
"""Answers the fact-check plugin puts above the results: the offer to check a
claim, and the no-model summary of what the reviewers found."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

__all__ = ["FactCheckOffer", "FactCheckSummary"]

from searx.result_types.answer import BaseAnswer


class FactCheckOffer(BaseAnswer, kw_only=True):
    """ "This reads like a claim. Check it?"  Shown on an ordinary search when
    the heuristic fires.  :py:attr:`url` runs the same query in fact-check mode."""

    template: str = "answer/fork_factcheck_offer.html"
    query: str

    def __hash__(self):
        return hash((self.template, self.query))


class FactCheckSummary(BaseAnswer, kw_only=True):
    """What the reviewers found, counted, with no model involved.  This line is
    the product's verdict when the model layer is off.  :py:attr:`url` runs the
    query as an ordinary web search."""

    template: str = "answer/fork_factcheck_summary.html"
    query: str
    reviews: int = 0
    """Number of claim reviews on the page."""
    reviewers: int = 0
    """Number of distinct fact-checking organisations among them."""
    claims: int = 0
    """Number of distinct claims (near-duplicate claim texts are one claim)."""
    counts: list[tuple[str, int]] = []
    """``(verdict, count)`` pairs, harshest verdict first, zero counts left out."""

    def __hash__(self):
        return hash((self.template, self.query))
