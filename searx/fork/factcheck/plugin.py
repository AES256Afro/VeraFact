# SPDX-License-Identifier: AGPL-3.0-or-later
"""The fact-check plugin: ranking in fact-check mode, the no-model summary,
and the offer banner on ordinary searches.

Registered in ``settings.yml`` under ``plugins:`` like any upstream plugin.
"""

from __future__ import annotations

__all__ = ["SXNGPlugin", "cluster_claims", "normalise_claim"]

import re
import typing as t
from collections import Counter
from urllib.parse import urlencode

from flask_babel import gettext

from searx import get_setting
from searx.fork.factcheck import trigger
from searx.fork.factcheck.verdicts import is_reviewer_host, severity
from searx.fork.result_types import ClaimReview, FactCheckOffer, FactCheckSummary
from searx.plugins import Plugin, PluginInfo
from searx.result_types import EngineResults
from searx.result_types._base import MainResult

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Request
    from searx.plugins import PluginCfg
    from searx.result_types import Result
    from searx.search import SearchWithPlugins

JACCARD_THRESHOLD = 0.6
"""Two claim texts whose token sets overlap at least this much are one claim."""

_STOPWORDS = frozenset(
    "a an the of to in on at for and or but is are was were be been being that this these those it its "
    "as by with from than then so if not no yes he she they them his her their we you i our your "
    "has have had do does did will would can could should may might must about into over under".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def normalise_claim(text: str) -> frozenset[str]:
    """The token set used to compare two claim texts."""
    return frozenset(tok for tok in _TOKEN.findall((text or "").lower()) if tok not in _STOPWORDS and len(tok) > 1)


def cluster_claims(reviews: list[ClaimReview]) -> list[list[ClaimReview]]:
    """Group reviews whose claims are near-duplicates (greedy, by token
    Jaccard).  Clusters with more reviewers come first."""
    clusters: list[tuple[frozenset[str], list[ClaimReview]]] = []
    for review in reviews:
        tokens = normalise_claim(review.claim or review.title)
        for key, members in clusters:
            union = len(key | tokens)
            if union and len(key & tokens) / union >= JACCARD_THRESHOLD:
                members.append(review)
                break
        else:
            clusters.append((tokens, [review]))
    ordered = sorted(clusters, key=lambda c: len({m.reviewer for m in c[1]}), reverse=True)
    return [members for _, members in ordered]


class SXNGPlugin(Plugin):
    """Fact-check mode.  Keeps fact-checker results only, groups reviews of
    the same claim, and sums the verdicts up in one line.  On an ordinary
    search it offers the mode when the query reads like a claim."""

    id = "factcheck"

    def __init__(self, plg_cfg: "PluginCfg") -> None:
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name=gettext("Fact check"),
            description=gettext(
                "In fact-check mode, lays results out as claim, verdict and source and sums the reviews up. "
                "On an ordinary search, offers the mode when the query reads like a claim."
            ),
            preference_section="general",
        )

    def on_result(self, request: "SXNG_Request", search: "SearchWithPlugins", result: "Result") -> bool:
        if not trigger.is_strict_mode(search.search_query.categories):
            return True
        if isinstance(result, ClaimReview):
            return True
        if isinstance(result, MainResult):
            return is_reviewer_host(result.url or "")
        return True

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        results = EngineResults()
        query = search.search_query.query
        if search.search_query.pageno > 1:
            return results

        if not trigger.is_factcheck_mode(search.search_query.categories):
            if get_setting("fork.factcheck.offer_on_heuristic", True) and trigger.looks_like_claim(query):
                results.add(FactCheckOffer(query=query, link=_search_url(request, query, trigger.MODE_FACTCHECK)))
            return results

        reviews = [r for r in search.result_container.main_results_map.values() if isinstance(r, ClaimReview)]
        clusters = cluster_claims(reviews)
        for members in clusters:
            if len({m.reviewer for m in members}) >= 2:
                for member in members:
                    member.priority = "high"

        counts = Counter(r.verdict for r in reviews)
        results.add(
            FactCheckSummary(
                query=query,
                link=_search_url(request, query, trigger.MODE_SEARCH),
                reviews=len(reviews),
                reviewers=len({r.reviewer for r in reviews if r.reviewer}),
                claims=len(clusters),
                counts=sorted(counts.items(), key=lambda item: severity(item[0])),
            )
        )
        return results


def _search_url(request: "SXNG_Request", query: str, mode: str) -> str:
    """``/search?q=…&mode=…`` relative to where the app is mounted.  Built by
    hand because Flask's ``url_for`` is not reliable from inside a plugin
    (it produced ``http:///search`` behind the container's proxy)."""
    root = (getattr(request, "script_root", "") or "").rstrip("/")
    return f"{root}/search?{urlencode({'q': query, trigger.MODE_FIELD: mode})}"
