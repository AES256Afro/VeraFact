# SPDX-License-Identifier: AGPL-3.0-or-later
"""ClaimReview enrichment: read a fact-check article's schema.org JSON-LD and
fill the rating, claim and dates of an *unrated* review.

Fact-checkers embed ``ClaimReview`` as ``<script type="application/ld+json">``.
Tier 2 listings without a rating and every tier 3 hit arrive unrated; for the
first few of them the plugin fetches the page once (bounded: N pages, a short
timeout, all in parallel), parses the markup here and caches what it found by
URL for a week.  A page without ClaimReview is cached too, as "nothing", so it
is not fetched again.
"""

from __future__ import annotations

__all__ = ["extract_claim_reviews", "claim_review_fields", "enrich", "fetch_pages"]

import json
import re
import typing as t
from collections.abc import Callable, Iterable

from searx import logger as _searx_logger
from searx.enginelib import EngineCache
from searx.fork.factcheck.verdicts import normalise, normalise_rating, reviewer_name
from searx.fork.result_types import ClaimReview

logger = _searx_logger.getChild("fork.factcheck.claimreview")

CACHE_EXPIRE = 7 * 24 * 3600
CACHE = EngineCache("factcheck_enrich", expire=CACHE_EXPIRE)

_LDJSON = re.compile(r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->|^\s*//<!\[CDATA\[|//\]\]>\s*$", re.S)

Fetcher = Callable[[list[str], float], dict[str, str | None]]
"""``fetch(urls, timeout) -> {url: html or None}``; injected in tests."""


def _walk(node: t.Any, found: list[dict[str, t.Any]]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, found)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "ClaimReview" in kinds:
            found.append(node)
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                _walk(node[key], found)


def extract_claim_reviews(html_text: str) -> list[dict[str, t.Any]]:
    """Every ``ClaimReview`` object in the page's JSON-LD blocks, in order."""
    found: list[dict[str, t.Any]] = []
    for block in _LDJSON.findall(html_text or ""):
        block = _COMMENT.sub("", block).strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except ValueError:
            continue
        _walk(data, found)
    return found


def _name(node: t.Any) -> str:
    if isinstance(node, list):
        return ", ".join(n for n in (_name(x) for x in node) if n)
    if isinstance(node, dict):
        return str(node.get("name") or "")
    if isinstance(node, str):
        return node
    return ""


def _date(value: t.Any) -> str:
    return str(value or "")[:10]


def claim_review_fields(data: dict[str, t.Any], url: str = "") -> dict[str, str]:
    """The :py:class:`ClaimReview` fields a JSON-LD ``ClaimReview`` object gives."""
    rating = data.get("reviewRating") or {}
    if not isinstance(rating, dict):
        rating = {}
    verdict_raw = str(rating.get("alternateName") or rating.get("name") or "").strip()
    verdict = normalise(verdict_raw) if verdict_raw else "unrated"
    if verdict == "unrated" and rating.get("ratingValue") not in (None, ""):
        verdict = normalise_rating(rating.get("ratingValue"), rating.get("bestRating"), rating.get("worstRating"))

    item = data.get("itemReviewed") or {}
    if not isinstance(item, dict):
        item = {}
    claimant = _name(item.get("author"))
    reviewer = (
        _name(data.get("author")) or _name(data.get("publisher")) or reviewer_name(url or str(data.get("url") or ""))
    )

    return {
        "claim": " ".join(str(data.get("claimReviewed") or "").split()),
        "claimant": claimant,
        "claim_date": _date(item.get("datePublished")),
        "verdict_raw": verdict_raw,
        "verdict": verdict,
        "reviewer": reviewer,
        "review_date": _date(data.get("datePublished")),
    }


def fetch_pages(urls: list[str], timeout: float) -> dict[str, str | None]:
    """Fetch ``urls`` in parallel through SearXNG's outgoing network; a page that
    fails or times out is ``None``."""
    from searx.network import Request, multi_requests  # pylint: disable=import-outside-toplevel
    from searx.utils import gen_useragent  # pylint: disable=import-outside-toplevel

    headers = {"User-Agent": gen_useragent(), "Accept": "text/html,application/xhtml+xml"}
    responses = multi_requests([Request.get(u, timeout=timeout, headers=headers) for u in urls])
    out: dict[str, str | None] = {}
    for url, resp in zip(urls, responses):
        if isinstance(resp, Exception) or getattr(resp, "status_code", 0) != 200:
            out[url] = None
        else:
            out[url] = resp.text
    return out


def _apply(review: ClaimReview, fields: dict[str, str]) -> None:
    for name, value in fields.items():
        if not value or value == "unrated":
            continue
        if name in ("verdict", "verdict_raw") or not getattr(review, name):
            setattr(review, name, value)


def enrich(
    reviews: Iterable[ClaimReview],
    *,
    max_fetch: int,
    timeout: float = 3.0,
    fetch: Fetcher = fetch_pages,
) -> int:
    """Fill the first ``max_fetch`` unrated reviews that have a URL from their
    article's ClaimReview markup.  Returns how many got a verdict."""
    todo = [r for r in reviews if r.verdict == "unrated" and r.url][: max(0, int(max_fetch))]
    if not todo:
        return 0

    enriched = 0
    to_fetch: list[ClaimReview] = []
    for review in todo:
        cached = CACHE.get(str(review.url))
        if cached is None:
            to_fetch.append(review)
            continue
        if cached:
            _apply(review, cached)
            enriched += review.verdict != "unrated"

    if to_fetch:
        pages = fetch([str(r.url) for r in to_fetch], timeout)
        for review in to_fetch:
            page = pages.get(str(review.url))
            if page is None:
                continue  # not cached: try again next time
            found = extract_claim_reviews(page)
            fields = claim_review_fields(found[0], str(review.url)) if found else {}
            CACHE.set(str(review.url), fields)
            if fields:
                _apply(review, fields)
                enriched += review.verdict != "unrated"
    return enriched
