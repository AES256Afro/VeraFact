# SPDX-License-Identifier: AGPL-3.0-or-later
"""WordPress REST search of a fact-checker's site (VeraFact, tier 2).

Many fact-checkers run WordPress with the REST API on: ``/wp-json/wp/v2/search``
returns ``[{"title", "url", ...}]`` for a query, with no key and no scraping.
The listing has no rating, so every hit is *unrated* until the fact-check
plugin enriches it from the article's ClaimReview JSON-LD.

Configuration
=============

.. code:: yaml

   - name: factcheck.org
     engine: factcheck_wordpress
     base_url: https://www.factcheck.org
     reviewer: FactCheck.org      # optional; else the known-reviewer list by host
     shortcut: fco
"""

from __future__ import annotations

import html
import typing as t
from urllib.parse import urlencode

from searx.fork.factcheck.verdicts import reviewer_name
from searx.fork.result_types import ClaimReview
from searx.result_types import EngineResults

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

about = {
    "website": None,
    "wikidata_id": None,
    "official_api_documentation": "https://developer.wordpress.org/rest-api/reference/search-results/",
    "use_official_api": True,
    "require_api_key": False,
    "results": "JSON",
}

engine_type = "online"
categories = ["fact check"]
paging = True
page_size = 20

base_url = ""
"""The site, for example ``https://www.factcheck.org``.  Required."""
reviewer = ""
"""Display name of the organisation; defaults to the known-reviewer list by host."""


def setup(engine_settings: dict[str, t.Any]) -> bool:
    if not engine_settings.get("base_url"):
        raise ValueError("factcheck_wordpress: base_url is required")
    return True


def request(query: str, params: "OnlineParams") -> None:
    args = {"search": query, "per_page": page_size, "page": params.get("pageno") or 1, "type": "post"}
    params["url"] = f"{base_url.rstrip('/')}/wp-json/wp/v2/search?{urlencode(args)}"
    params["raise_for_httperror"] = False


def response(resp: "SXNG_Response") -> EngineResults:
    res = EngineResults()
    if resp.status_code == 400:
        # WordPress answers 400 for a page past the last one
        return res
    data: t.Any = resp.json()
    if not isinstance(data, list):
        return res
    for item in data:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url:
            continue
        title = " ".join(html.unescape(str(item.get("title") or "")).split())
        res.add(
            ClaimReview(
                url=str(url),
                title=title,
                claim=title,
                reviewer=reviewer or reviewer_name(str(url)),
            )
        )
    return res
