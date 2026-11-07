# SPDX-License-Identifier: AGPL-3.0-or-later
"""Result types the fork adds.  They are plain :py:mod:`searx.result_types`
structs; engines import them from here."""

__all__ = ["ClaimReview", "Verdict", "VERDICTS"]

from .claim_review import ClaimReview, Verdict, VERDICTS
