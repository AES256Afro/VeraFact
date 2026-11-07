# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ways into fact-check mode, and the claim heuristic.

Fact-check mode *is* the ``fact check`` category: when it is selected, the
fact-check engines run and the ranking plugin lays the page out as claim →
verdict → source.  This module maps the three ways a user asks for it onto
that category:

- the ``mode`` form field (``factcheck`` or ``search``) set by the switch on
  the home page and the results header;
- a ``!fc`` or ``!factcheck`` bang at the start or end of the query
  (``!fact_check`` already works upstream because it names the category);
- nothing at all: :py:func:`looks_like_claim` only *offers* the mode on the
  results page, it never switches silently.

:py:func:`adapt_form` is the one hook in ``searx/webadapter.py``.
"""

from __future__ import annotations

__all__ = ["CATEGORY", "adapt_form", "is_factcheck_mode", "is_strict_mode", "looks_like_claim"]

import re
import typing as t
from collections.abc import Iterable, Mapping

CATEGORY = "fact check"
"""The category that is fact-check mode."""

MODE_FIELD = "mode"
MODE_FACTCHECK = "factcheck"
MODE_SEARCH = "search"

BANGS = ("!fc", "!factcheck")

_CATEGORY_FIELD = "category_" + CATEGORY


def _strip_bang(query: str) -> tuple[str, bool]:
    words = query.split()
    if len(words) < 2:
        # a bang with nothing after it is not a query; leave it to upstream
        return query, False
    for bang in BANGS:
        if words[0].lower() == bang:
            return " ".join(words[1:]), True
        if words[-1].lower() == bang:
            return " ".join(words[:-1]), True
    return query, False


def adapt_form(form: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of the request form with the mode resolved into
    categories.

    - ``mode=factcheck`` (or a bang in ``q``) replaces every category field
      with the ``fact check`` category.
    - ``mode=search`` removes the ``fact check`` category; what is left, or
      the user's defaults, applies.
    - anything else passes through unchanged.
    """
    out: dict[str, str] = dict(form.items())
    mode = (out.get(MODE_FIELD) or "").strip().lower()

    query, bang = _strip_bang(out.get("q") or "")
    if bang:
        out["q"] = query
        mode = MODE_FACTCHECK

    if mode == MODE_FACTCHECK:
        for key in list(out):
            if key == "categories" or key.startswith("category_"):
                del out[key]
        out[_CATEGORY_FIELD] = "1"
    elif mode == MODE_SEARCH:
        out.pop(_CATEGORY_FIELD, None)
        if "categories" in out:
            kept = [c.strip() for c in out["categories"].split(",") if c.strip() and c.strip() != CATEGORY]
            if kept:
                out["categories"] = ",".join(kept)
            else:
                del out["categories"]
    out.pop(MODE_FIELD, None)
    return out


def is_factcheck_mode(categories: Iterable[str]) -> bool:
    """True when the ``fact check`` category is among the search's categories."""
    return CATEGORY in set(categories)


def is_strict_mode(categories: Iterable[str]) -> bool:
    """True when ``fact check`` is the *only* category: results from
    non-fact-checker hosts are then dropped."""
    return set(categories) == {CATEGORY}


_LEADS = re.compile(
    r"^(is it true|is this true|is that true|is it real|was it true|true or false|fact[ -]?check|debunk|hoax|"
    r"did .{1,80}? (really|actually)|does .{1,80}? (really|actually)|do .{1,80}? (really|actually)|"
    r"has .{1,80}? (really|actually)|have .{1,80}? (really|actually)|are .{1,80}? (really|actually))\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'^\s*["“].{12,}["”]\s*$')
_VERBISH = re.compile(
    r"\b(is|are|was|were|has|have|had|will|would|can|could|did|does|do|said|says|claims?|caused?|"
    r"kills?|killed|contains?|found|proves?|shows?|means|made|makes|banned|signed|announced|died|"
    r"won|lost|paid|owns?|admits?|admitted|confirms?|confirmed|declared|voted)\b",
    re.IGNORECASE,
)


def looks_like_claim(query: str) -> bool:
    """A cheap, deliberately conservative guess at whether ``query`` is a claim
    rather than a search.  False positives cost one banner; false negatives
    cost nothing, so precision matters more than recall."""
    q = " ".join((query or "").split())
    if not q:
        return False
    if _LEADS.search(q):
        return True
    if _QUOTED.match(q):
        return True
    words = q.split()
    if len(words) >= 12 and q.endswith(".") and _VERBISH.search(q):
        return True
    return False
