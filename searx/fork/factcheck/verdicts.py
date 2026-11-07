# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalising reviewers' rating words, and the list of known reviewers.

The data is ``verdicts.yml`` next to this module.  Nothing here touches the
network; it is pure string work so it can be tested exhaustively.
"""

from __future__ import annotations

__all__ = ["normalise", "normalise_rating", "reviewer_name", "is_reviewer_host", "severity", "REVIEWERS"]

import pathlib
import re
import typing as t

import yaml

from searx.fork.factcheck.verdict_types import Verdict, VERDICTS

_DATA_FILE = pathlib.Path(__file__).parent / "verdicts.yml"

with _DATA_FILE.open(encoding="utf-8") as _f:
    _DATA: dict[str, t.Any] = yaml.safe_load(_f)

REVIEWERS: dict[str, str] = {str(k).lower(): str(v) for k, v in _DATA.get("reviewers", {}).items()}
"""Known fact-checking hosts (without ``www.``) and the name to show for each."""

_SEVERITY: dict[str, int] = {
    "false": 0,
    "mostly-false": 1,
    "misleading": 2,
    "mixed": 3,
    "unproven": 4,
    "outdated": 5,
    "satire": 6,
    "mostly-true": 7,
    "true": 8,
    "unrated": 9,
}


def _phrase_table() -> tuple[dict[str, Verdict], list[tuple[re.Pattern[str], Verdict]]]:
    exact: dict[str, Verdict] = {}
    phrases: list[tuple[str, Verdict]] = []
    for name, words in _DATA.get("verdicts", {}).items():
        if name not in VERDICTS:
            raise ValueError(f"verdicts.yml: unknown verdict {name!r}")
        verdict = t.cast(Verdict, name)
        for word in words:
            phrase = _clean(str(word))
            exact.setdefault(phrase, verdict)
            phrases.append((phrase, verdict))
    # longest phrase first, so "mostly false" wins over "false"
    phrases.sort(key=lambda item: len(item[0]), reverse=True)
    compiled: list[tuple[re.Pattern[str], Verdict]] = [
        (re.compile(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])"), v) for p, v in phrases
    ]
    return exact, compiled


def _clean(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = " ".join(text.split())
    return text


_EXACT, _PHRASES = _phrase_table()

_QUINTILES: tuple[tuple[float, Verdict], ...] = (
    (0.8, "true"),
    (0.6, "mostly-true"),
    (0.4, "mixed"),
    (0.2, "mostly-false"),
)


def normalise(raw: str) -> Verdict:
    """Map a reviewer's rating text onto a :py:obj:`Verdict`.

    Whole-phrase matches win, then the longest phrase found inside the text
    (bounded by non-letters, so *untrue* never matches *true*).  Anything
    else is ``unrated``.
    """
    text = _clean(raw or "")
    if not text:
        return "unrated"
    stripped = text.strip(" .!:;-")
    if stripped in _EXACT:
        return _EXACT[stripped]
    for pattern, verdict in _PHRASES:
        if pattern.search(text):
            return verdict
    return "unrated"


def normalise_rating(value: t.Any, best: t.Any, worst: t.Any) -> Verdict:
    """Map a numeric ``ratingValue`` with its ``bestRating`` / ``worstRating``
    onto a verdict by quintile.  Non-numeric or degenerate input is ``unrated``."""
    try:
        v, b, w = float(value), float(best), float(worst)
    except (TypeError, ValueError):
        return "unrated"
    if b == w:
        return "unrated"
    # works for both directions of the scale (best may be the smaller number)
    frac = max(0.0, min(1.0, (v - w) / (b - w)))
    for threshold, verdict in _QUINTILES:
        if frac >= threshold:
            return verdict
    return "false"


def severity(verdict: str) -> int:
    """Order for sorting: the harshest verdict first, ``unrated`` last."""
    return _SEVERITY.get(verdict, len(_SEVERITY))


def _host(host_or_url: str) -> str:
    host = host_or_url.lower().strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def reviewer_name(host_or_url: str) -> str:
    """The display name of a known reviewer for ``host_or_url``, else ``""``.
    Sub-domains match their parent (``factcheck.afp.com`` is listed on its own
    because its name differs from ``afp.com``)."""
    host = _host(host_or_url)
    while host:
        if host in REVIEWERS:
            return REVIEWERS[host]
        if "." not in host:
            break
        host = host.split(".", 1)[1]
    return ""


def is_reviewer_host(host_or_url: str) -> bool:
    """True when ``host_or_url`` belongs to a known fact-checking organisation."""
    return bool(reviewer_name(host_or_url))
