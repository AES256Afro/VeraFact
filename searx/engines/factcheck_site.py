# SPDX-License-Identifier: AGPL-3.0-or-later
"""Site-scoped fallback for a fact-checker (VeraFact, tier 3 of fact-check mode).

A wrapper around a general engine: it prepends ``site:<site>`` to the query,
hands the request to the base engine, and turns the hits from that site into
:py:class:`~searx.fork.result_types.ClaimReview` results (unrated until the
fact-check plugin enriches them from the article's ClaimReview JSON-LD).

Used for sites whose own search is client-rendered or walled (Snopes, Full
Fact, AFP, Lead Stories) and as the safety net when a tier 2 engine breaks.

Configuration
=============

.. code:: yaml

   - name: snopes
     engine: factcheck_site
     site: snopes.com
     base_engine: yahoo          # any general engine with request()/response()
     shortcut: snp
"""

from __future__ import annotations

import typing as t

import searx.engines
from searx import get_setting
from searx.fork.factcheck.verdicts import reviewer_name
from searx.fork.result_types import ClaimReview
from searx.result_types import EngineResults
from searx.result_types._base import MainResult

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

about = {
    "website": None,
    "wikidata_id": None,
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

engine_type = "online"
categories = ["fact check"]
paging = False
time_range_support = False
safesearch = False

site = ""
"""Host to scope the search to, for example ``snopes.com``.  Required."""
base_engine = "yahoo"
"""Name of the general engine that runs the ``site:`` query.  Yahoo answers
site-scoped queries from a home connection without a challenge; DuckDuckGo,
Google and Qwant did not when this was written, and Brave rate-limits after a
few requests.  Set it per engine in ``settings.yml``."""
reviewer = ""
"""Display name; defaults to the known-reviewer list by host."""

_base: t.Any = None


def setup(engine_settings: dict[str, t.Any]) -> bool:
    if not engine_settings.get("site"):
        raise ValueError("factcheck_site: site is required")
    return True


def _resolve_base() -> t.Any:
    """The base engine: the registered one when it is enabled (it then has its
    traits, cache and settings), else a private copy built the way the engine
    loader builds every engine (defaults, traits, setup), without registering it."""
    global _base  # pylint: disable=global-statement
    if _base is not None:
        return _base
    registered = searx.engines.engines.get(base_engine)
    if registered is not None:
        _base = registered
        return _base
    # Not registered (disabled with `inactive`, or failed its own setup). Build a
    # private copy from its settings.yml entry when there is one (that also
    # covers engines defined on top of the xpath / json engines), else from the
    # module of the same name. Engine names may not contain underscores, and
    # this name is never registered.
    private_name = "vf " + base_engine.replace("_", " ")
    entry: dict[str, t.Any] | None = next(
        (dict(e) for e in get_setting("engines", []) if e.get("name") == base_engine), None
    )
    if entry is None:
        entry = {"engine": base_engine, "shortcut": f"vf-{base_engine}", "categories": ["general"]}
    entry.update({"name": private_name, "inactive": False, "disabled": False})
    module = searx.engines.load_engine(entry)
    if module is None:
        raise ValueError(f"factcheck_site: base engine {base_engine!r} could not be loaded")
    _base = module
    return _base


def _same_site(url: str) -> bool:
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return host == site or host.endswith("." + site)


def request(query: str, params: "OnlineParams") -> None:
    _resolve_base().request(f"site:{site} {query}", params)


def response(resp: "SXNG_Response") -> EngineResults:
    res = EngineResults()
    for item in _resolve_base().response(resp) or []:
        if isinstance(item, MainResult):
            url, title, content, published = item.url, item.title, item.content, item.publishedDate
        elif isinstance(item, dict):
            url, title, content, published = (
                item.get("url"),
                item.get("title", ""),
                item.get("content", ""),
                item.get("publishedDate"),
            )
        else:
            continue
        if not url or not _same_site(str(url)):
            continue
        res.add(
            ClaimReview(
                url=str(url),
                title=str(title or ""),
                content=str(content or ""),
                claim=str(title or ""),
                reviewer=reviewer or reviewer_name(str(url)),
                publishedDate=published,
            )
        )
    return res
