# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google Fact Check Tools API (VeraFact, tier 1 of fact-check mode).

The API aggregates the ``ClaimReview`` markup that IFCN signatories publish
with their articles, so one request reaches PolitiFact, Snopes, FactCheck.org,
Full Fact, AFP, Reuters, AP, Lead Stories and many more.  Every hit becomes a
:py:class:`~searx.fork.result_types.ClaimReview`.

It needs an API key from a Google Cloud project with the *Fact Check Tools
API* enabled.  The key comes from ``fork.factcheck.google_api_key`` in
``settings.yml`` or the ``FORK_FACTCHECK_GOOGLE_API_KEY`` environment variable;
without one the engine is not loaded.

This module lives in ``searx/engines/`` because upstream's engine loader only
looks there; the fact-check logic it uses is in ``searx/fork/factcheck/``.
"""

from __future__ import annotations

import typing as t
from urllib.parse import urlencode

from dateutil import parser as dateparser

from searx import get_setting
from searx.fork.result_types import ClaimReview
from searx.result_types import EngineResults

if t.TYPE_CHECKING:
    import logging

    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

    logger = logging.getLogger()

about = {
    "website": "https://toolbox.google.com/factcheck/explorer",
    "wikidata_id": None,
    "official_api_documentation": "https://developers.google.com/fact-check/tools/api/reference/rest",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
}

engine_type = "online"
categories = ["fact check"]
paging = False
page_size = 20
base_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

api_key = ""
"""Filled in :py:func:`setup` from the fork settings; never from ``settings.yml``'s engine entry."""


def setup(engine_settings: dict[str, t.Any]) -> bool:  # pylint: disable=unused-argument
    """Load the key from the fork settings.  Returns ``False`` (engine not
    loaded) when there is none."""
    global api_key  # pylint: disable=global-statement
    key = get_setting("fork.factcheck.google_api_key", "") or ""
    if not key:
        logger.info("no fork.factcheck.google_api_key (or FORK_FACTCHECK_GOOGLE_API_KEY): engine not loaded")
        return False
    api_key = key
    return True


def request(query: str, params: "OnlineParams") -> None:
    args: dict[str, str | int] = {"query": query, "pageSize": page_size, "key": api_key}
    locale = params.get("searxng_locale") or ""
    if locale and locale != "all":
        args["languageCode"] = locale.split("-")[0].split("_")[0]
    params["url"] = f"{base_url}?{urlencode(args)}"
    params["raise_for_httperror"] = True


def _iso_date(value: t.Any) -> str:
    return str(value or "")[:10]


def response(resp: "SXNG_Response") -> EngineResults:
    res = EngineResults()
    data: t.Any = resp.json()
    if not isinstance(data, dict):
        return res

    for claim in data.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        claim_text = str(claim.get("text") or "")
        claimant = str(claim.get("claimant") or "")
        claim_date = _iso_date(claim.get("claimDate"))

        for review in claim.get("claimReview") or []:
            if not isinstance(review, dict):
                continue
            url = review.get("url")
            if not url:
                continue
            publisher = review.get("publisher") or {}
            reviewer = str(publisher.get("name") or publisher.get("site") or "")
            review_date = _iso_date(review.get("reviewDate"))
            published = None
            if review_date:
                try:
                    published = dateparser.isoparse(str(review.get("reviewDate")))
                except (ValueError, TypeError, OverflowError):
                    published = None

            res.add(
                ClaimReview(
                    url=str(url),
                    title=str(review.get("title") or claim_text or reviewer),
                    content="",
                    claim=claim_text,
                    claimant=claimant,
                    claim_date=claim_date,
                    verdict_raw=str(review.get("textualRating") or ""),
                    reviewer=reviewer,
                    review_date=review_date,
                    publishedDate=published,
                )
            )
    return res
