# SPDX-License-Identifier: AGPL-3.0-or-later
"""PolitiFact site search (VeraFact, tier 2 of fact-check mode).

PolitiFact's search page is server-rendered and its fact-check listing
carries everything a :py:class:`~searx.fork.result_types.ClaimReview` needs:
the claim, who made it and when, the Truth-O-Meter rating (as the alt text of
the meter image) and the review date.  No key, no JSON-LD fetch.

Sites redesign; when the selectors below stop matching, the engine returns
nothing and the site-scoped fallback (``factcheck_site``) still covers it.
"""

from __future__ import annotations

import re
import typing as t
from urllib.parse import urlencode

from dateutil import parser as dateparser

from searx.fork.result_types import ClaimReview
from searx.result_types import EngineResults
from searx.utils import eval_xpath_getindex, eval_xpath_list, extract_text, html_to_text
from searx.utils import html as html_parser

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

about = {
    "website": "https://www.politifact.com",
    "wikidata_id": "Q7211058",
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

engine_type = "online"
categories = ["fact check"]
paging = False
# www.politifact.com answers with a 301, which engines do not follow; the bare host serves the page
search_url = "https://politifact.com/search/?{args}"
reviewer = "PolitiFact"

results_xpath = (
    '//div[contains(@class, "py-4") and contains(@class, "border-bottom")]'
    '[.//h5[contains(@class, "pf-search-factcheck-title")]]'
)
title_xpath = './/h5[contains(@class, "pf-search-factcheck-title")]/a'
url_xpath = './/h5[contains(@class, "pf-search-factcheck-title")]/a/@href'
claimant_xpath = './/div[contains(@class, "pf-search-personality-meta")]/a'
stated_xpath = './/div[contains(@class, "pf-search-personality-meta")]/span'
verdict_xpath = './/img[contains(@src, "meter")]/@alt'
review_date_xpath = './/span[contains(@class, "fw-light")]'

_STATED = re.compile(r"stated on (?P<date>.+?)(?: in (?P<where>.+?))?:?\s*$", re.IGNORECASE | re.DOTALL)


def request(query: str, params: "OnlineParams") -> None:
    params["url"] = search_url.format(args=urlencode({"q": query}))


def _text(nodes: list[t.Any]) -> str:
    return " ".join((extract_text(nodes) or "").split())


def _iso(text: str | None) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    try:
        return dateparser.parse(text).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return ""


def response(resp: "SXNG_Response") -> EngineResults:
    res = EngineResults()
    dom = html_parser.fromstring(resp.text)

    for item in eval_xpath_list(dom, results_xpath):
        url = eval_xpath_getindex(item, url_xpath, 0, default="")
        if not url:
            continue
        verdict_raw = html_to_text(str(eval_xpath_getindex(item, verdict_xpath, 0, default="")))
        if not verdict_raw and "/factchecks/" not in str(url):
            # a plain article in the listing, not a review of a claim
            continue
        claim = _text(eval_xpath_list(item, title_xpath))
        claimant = _text(eval_xpath_list(item, claimant_xpath))
        stated = _text(eval_xpath_list(item, stated_xpath))
        claim_date = ""
        where = ""
        m = _STATED.search(stated)
        if m:
            claim_date = _iso(m.group("date"))
            where = (m.group("where") or "").strip()
        review_date = _iso(_text(eval_xpath_list(item, review_date_xpath)))

        content = ""
        if claimant and where:
            content = f"{claimant}, {where}"
        elif claimant:
            content = claimant

        res.add(
            ClaimReview(
                url=str(url),
                title=claim,
                content=content,
                claim=claim,
                claimant=claimant,
                claim_date=claim_date,
                verdict_raw=verdict_raw,
                reviewer=reviewer,
                review_date=review_date,
            )
        )
    return res
