# SPDX-License-Identifier: AGPL-3.0-or-later
"""The *claim review* result: one fact-checker's review of one claim.

A :py:class:`ClaimReview` is a :py:class:`~searx.result_types.MainResult`
whose link is the review article and which carries the claim, the reviewer's
own rating text and a normalised verdict.  It renders through
:origin:`result_templates/fork_claim_review.html
<searx/templates/simple/result_templates/fork/claim_review.html>`.

The reviewer's words (:py:attr:`ClaimReview.verdict_raw`) are always kept and
shown; the normalised :py:attr:`ClaimReview.verdict` only drives the badge
colour and the ordering.  The mapping lives in ``searx/fork/factcheck/verdicts.yml``.
"""

# pylint: disable=too-few-public-methods

from __future__ import annotations

__all__ = ["ClaimReview", "Verdict", "VERDICTS"]

from searx.fork.factcheck.verdict_types import Verdict, VERDICTS
from searx.result_types._base import MainResult


class ClaimReview(MainResult, kw_only=True):
    """One reviewer's review of one claim."""

    template: str = "fork_claim_review.html"

    claim: str = ""
    """The claim as the reviewer states it (``claimReviewed``)."""

    claimant: str = ""
    """Who made the claim, when known."""

    claim_date: str = ""
    """When the claim was made, as the source gives it (ISO date or free text)."""

    verdict_raw: str = ""
    """The reviewer's own rating text, for example *Pants on Fire* or *Four Pinocchios*."""

    verdict: Verdict = "unrated"
    """The normalised verdict.  Filled from :py:attr:`verdict_raw` when the
    engine leaves it at ``unrated``."""

    reviewer: str = ""
    """The fact-checking organisation (publisher name)."""

    review_date: str = ""
    """When the review was published, as the source gives it."""

    def normalize_result_fields(self):
        super().normalize_result_fields()
        # avoid a cyclic import: verdicts needs this module's Verdict type
        from searx.fork.factcheck.verdicts import normalise  # pylint: disable=import-outside-toplevel

        if self.verdict == "unrated" and self.verdict_raw:
            self.verdict = normalise(self.verdict_raw)
        for name in ("claim", "claimant", "claim_date", "verdict_raw", "reviewer", "review_date"):
            value = getattr(self, name)
            if isinstance(value, str):
                setattr(self, name, " ".join(value.split()))
