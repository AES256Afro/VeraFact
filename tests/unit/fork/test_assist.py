# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

from unittest import mock

from searx.extended_types import sxng_request
from searx.fork import llm
from searx.fork.factcheck import assist
from tests import SearxTestCase


def llm_settings(**values):
    base = {
        "backend": "disabled",
        "model": "",
        "search_assist": False,
        "search_assist_default": False,
        "search_assist_local": False,
        "search_assist_max_fetches": 6,
        "search_assist_timeout": 8,
    }
    base.update(values)

    def fake(name, default=None):
        if name.startswith("fork.llm."):
            return base.get(name[len("fork.llm.") :], default)
        return default

    return [
        mock.patch("searx.fork.llm.get_setting", side_effect=fake),
        mock.patch("searx.fork.factcheck.assist.get_setting", side_effect=fake),
    ]


class StateTest(SearxTestCase):

    def run_with(self, values, path="/search?q=x"):
        patches = llm_settings(**values)
        for p in patches:
            p.start()
        try:
            with self.app.test_request_context(path):
                return assist.resolve_state(sxng_request), assist.switch_items(sxng_request, "x", "")
        finally:
            for p in patches:
                p.stop()

    def test_disabled_backend_is_off(self):
        state, items = self.run_with({})
        self.assertEqual(state, "off")
        self.assertEqual(items, [])

    def test_local_backend_defaults_to_summary(self):
        state, items = self.run_with({"backend": "openai_compat", "model": "m"})
        self.assertEqual(state, "summary")
        self.assertEqual([i["label"] for i in items], ["Off", "Local"])
        self.assertEqual([i["current"] for i in items], ["", "1"])
        self.assertEqual(items[0]["link"], "/search?q=x&assist=off")

    def test_frontier_with_assist_offers_answer(self):
        state, items = self.run_with({"backend": "anthropic", "search_assist": True})
        self.assertEqual(state, "summary")
        self.assertEqual([i["label"] for i in items], ["Off", "Frontier", "Answer"])
        state, _ = self.run_with({"backend": "anthropic", "search_assist": True, "search_assist_default": True})
        self.assertEqual(state, "answer")

    def test_form_wins(self):
        state, _ = self.run_with({"backend": "openai_compat", "model": "m"}, "/search?q=x&assist=off")
        self.assertEqual(state, "off")

    def test_answer_clamped(self):
        state, _ = self.run_with({"backend": "openai_compat", "model": "m"}, "/search?q=x&assist=answer")
        self.assertEqual(state, "summary")
        state, _ = self.run_with(
            {"backend": "openai_compat", "model": "m", "search_assist": True, "search_assist_local": True},
            "/search?q=x&assist=answer",
        )
        self.assertEqual(state, "answer")

    def test_cookie_is_read(self):
        patches = llm_settings(backend="anthropic", search_assist=True)
        for p in patches:
            p.start()
        try:
            with self.app.test_request_context("/search?q=x", headers={"Cookie": "vf_assist=answer"}):
                self.assertEqual(assist.resolve_state(sxng_request), "answer")
            with self.app.test_request_context("/search?q=x", headers={"Cookie": "vf_assist=bogus"}):
                self.assertEqual(assist.resolve_state(sxng_request), "summary")
        finally:
            for p in patches:
                p.stop()

    def test_cookie_set_on_choice(self):
        patches = llm_settings(backend="openai_compat", model="m")
        for p in patches:
            p.start()
        try:
            resp = self.client.get("/search?q=test&assist=off")
            self.assertEqual(resp.status_code, 200)
            cookies = resp.headers.getlist("Set-Cookie")
            self.assertTrue(any(c.startswith("vf_assist=off") for c in cookies), cookies)
        finally:
            for p in patches:
                p.stop()


class AnswerTest(SearxTestCase):

    def test_answer_needs_citation(self):
        patches = llm_settings(backend="anthropic", search_assist=True)
        reply = llm.SearchAnswer(text="Trust me.", citations=[], fetched=[], latency_ms=5)
        with patches[0], patches[1], mock.patch("searx.fork.llm.web_search", return_value=reply):
            answer = assist.request_answer("q")
        self.assertFalse(answer.available)
        self.assertIn("cited nothing", answer.reason)

    def test_answer_kept_with_citation(self):
        patches = llm_settings(
            backend="anthropic", search_assist=True, search_assist_max_fetches=3, search_assist_timeout=4
        )
        reply = llm.SearchAnswer(
            text=" Yes. ", citations=[{"url": "https://a.example/", "title": "A"}], fetched=["a.example"], latency_ms=5
        )
        with patches[0], patches[1], mock.patch("searx.fork.llm.web_search", return_value=reply) as ws:
            answer = assist.request_answer("q", hide_link="/search?q=q&assist=summary")
        self.assertTrue(answer.available)
        self.assertEqual(answer.text, "Yes.")
        self.assertEqual(answer.fetched, ["a.example"])
        self.assertEqual(answer.hide_link, "/search?q=q&assist=summary")
        self.assertEqual(ws.call_args.kwargs, {"max_fetches": 3, "timeout": 4.0})

    def test_answer_not_allowed(self):
        patches = llm_settings(backend="openai_compat", model="m")
        with patches[0], patches[1], mock.patch("searx.fork.llm.web_search") as ws:
            answer = assist.request_answer("q")
        ws.assert_not_called()
        self.assertFalse(answer.available)


class RouteTest(SearxTestCase):

    def test_llm_test_route_disabled(self):
        resp = self.client.get("/fork/llm/test.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["backend"], "disabled")
        self.assertFalse(data["ok"])

    def test_preferences_model_section(self):
        resp = self.client.get("/preferences")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'id="pref_fork_llm"', resp.data)
        self.assertIn(b"No model is configured", resp.data)
