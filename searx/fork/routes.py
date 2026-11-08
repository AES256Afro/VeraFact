# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the fork registers on the Flask app, with one call from ``webapp.py``.

- ``GET /fork/llm/test.json``: the preferences page's *Test* button.  Sends
  one short prompt to the configured model and reports the latency, or the
  error, as JSON.
- the Jinja global ``vf_assist_switch(q, selected_categories)``: the entries
  of the Model assist switch for the current request (empty with no model).
"""

from __future__ import annotations

__all__ = ["register"]

import typing as t
from collections.abc import Iterable

from flask import Flask, jsonify

from searx.extended_types import sxng_request
from searx.fork import llm
from searx.fork.factcheck import assist, trigger


def llm_test() -> t.Any:
    return jsonify(llm.ping())


def assist_switch(query: str | None, selected_categories: Iterable[str] | None) -> list[dict[str, str]]:
    if not query:
        return []
    mode = trigger.MODE_FACTCHECK if trigger.is_factcheck_mode(selected_categories or []) else ""
    return assist.switch_items(sxng_request, query, mode)


def register(app: Flask) -> None:
    app.add_url_rule("/fork/llm/test.json", methods=["GET"], endpoint="fork_llm_test", view_func=llm_test)
    app.add_template_global(assist_switch, name="vf_assist_switch")
