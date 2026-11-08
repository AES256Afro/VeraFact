# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ``disabled`` backend: never called; :py:func:`searx.fork.llm.complete`
raises :py:class:`~searx.fork.llm.LlmDisabled` before it gets here.  The module
exists so the backend table in the docs is complete."""

from __future__ import annotations

import typing as t

from searx.fork.llm.types import Completion, LlmDisabled, Message


def complete(messages: list[Message], **kwargs: t.Any) -> Completion:  # pylint: disable=unused-argument
    raise LlmDisabled("fork.llm.backend is disabled")
