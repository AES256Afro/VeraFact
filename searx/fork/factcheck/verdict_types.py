# SPDX-License-Identifier: AGPL-3.0-or-later
"""The normalised verdict vocabulary.  A module of its own so the result type
and the normaliser can both import it without importing each other."""

__all__ = ["Verdict", "VERDICTS"]

import typing as t

Verdict = t.Literal[
    "true",
    "mostly-true",
    "mixed",
    "mostly-false",
    "false",
    "misleading",
    "unproven",
    "satire",
    "outdated",
    "unrated",
]

VERDICTS: tuple[str, ...] = t.get_args(Verdict)
"""Every normalised verdict.  Sorting order is :py:func:`searx.fork.factcheck.verdicts.severity`."""
