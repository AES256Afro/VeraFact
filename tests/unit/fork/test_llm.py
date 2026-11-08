# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import json
from unittest import mock

from searx.fork import llm
from searx.fork.llm import backends
from searx.fork.llm.backends import anthropic as anthropic_backend
from searx.fork.llm.backends import openai as openai_backend
from searx.fork.llm.backends import openai_compat
from tests import SearxTestCase

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


def settings(**values):
    """Patch fork.llm.* for one test."""
    base = {
        "backend": "disabled",
        "base_url": "",
        "model": "",
        "api_key": "",
        "timeout": 20,
        "max_tokens": 400,
        "allow_images": False,
    }
    base.update(values)

    def fake_get_setting(name, default=None):
        if name.startswith("fork.llm."):
            return base.get(name[len("fork.llm.") :], default)
        return default

    return (
        mock.patch("searx.fork.llm.get_setting", side_effect=fake_get_setting),
        mock.patch("searx.fork.llm.backends.get_setting", side_effect=fake_get_setting),
        mock.patch("searx.fork.llm.backends.openai_compat.get_setting", side_effect=fake_get_setting),
    )


class ParseJsonTest(SearxTestCase):

    def test_parse(self):
        self.assertEqual(llm.parse_json_object('{"a": 1}'), {"a": 1})
        self.assertEqual(llm.parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(llm.parse_json_object('Sure! {"a": {"b": "}"}} trailing'), {"a": {"b": "}"}})
        self.assertIsNone(llm.parse_json_object("[1, 2]"))
        self.assertIsNone(llm.parse_json_object("nothing here"))
        self.assertIsNone(llm.parse_json_object(""))


class DisabledTest(SearxTestCase):

    def test_disabled(self):
        patches = settings()
        with patches[0], patches[1], patches[2]:
            self.assertFalse(llm.enabled())
            self.assertEqual(llm.backend_name(), "disabled")
            with self.assertRaises(llm.LlmDisabled):
                llm.complete([llm.Message(role="user", content="hi")])
            info = llm.ping()
            self.assertFalse(info["ok"])
            self.assertIn("disabled", info["error"])


class OpenAICompatTest(SearxTestCase):

    def setUp(self):
        super().setUp()
        self.patches = settings(backend="openai_compat", base_url="http://ollama:11434/v1/", model="qwen2.5:3b")
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def test_labels(self):
        self.assertTrue(llm.enabled())
        self.assertFalse(llm.is_frontier())
        self.assertEqual(llm.model_label(), "qwen2.5:3b, local")

    def test_complete_text(self):
        calls = []

        def fake_post(url, body, headers, timeout):
            calls.append((url, body, headers, timeout))
            return backends.HttpReply(
                status=200, data={"model": "qwen2.5:3b", "choices": [{"message": {"content": "ready"}}]}
            )

        with mock.patch.object(openai_compat, "http_post", side_effect=fake_post):
            reply = llm.complete(
                [llm.Message(role="system", content="s"), llm.Message(role="user", content="u")], timeout=7
            )
        self.assertEqual(reply.text, "ready")
        self.assertEqual(reply.backend, "openai_compat")
        url, body, headers, timeout = calls[0]
        self.assertEqual(url, "http://ollama:11434/v1/chat/completions")
        self.assertEqual(body["model"], "qwen2.5:3b")
        self.assertEqual(body["messages"], [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
        self.assertNotIn("Authorization", headers)
        self.assertEqual(timeout, 7.0)

    def test_schema_fallback_when_server_rejects_response_format(self):
        replies = iter(
            [
                backends.HttpReply(status=400, data={"error": "unknown field response_format"}),
                backends.HttpReply(status=200, data={"choices": [{"message": {"content": 'Here you go: {"a": 3}'}}]}),
            ]
        )
        bodies = []

        def fake_post(url, body, headers, timeout):  # pylint: disable=unused-argument
            bodies.append(json.loads(json.dumps(body)))
            return next(replies)

        with mock.patch.object(openai_compat, "http_post", side_effect=fake_post):
            reply = llm.complete([llm.Message(role="user", content="u")], json_schema=SCHEMA)
        self.assertEqual(reply.data, {"a": 3})
        self.assertIn("response_format", bodies[0])
        self.assertNotIn("response_format", bodies[1])
        self.assertEqual(bodies[1]["messages"][0]["role"], "system")
        self.assertIn("JSON schema", bodies[1]["messages"][0]["content"])

    def test_bad_json_is_an_error(self):
        with mock.patch.object(
            openai_compat,
            "http_post",
            return_value=backends.HttpReply(status=200, data={"choices": [{"message": {"content": "no json"}}]}),
        ):
            with self.assertRaises(llm.LlmError):
                llm.complete([llm.Message(role="user", content="u")], json_schema=SCHEMA)

    def test_http_error(self):
        with mock.patch.object(openai_compat, "http_post", return_value=backends.HttpReply(status=500, data="boom")):
            with self.assertRaises(llm.LlmError):
                llm.complete([llm.Message(role="user", content="u")])

    def test_no_web_search_locally(self):
        with self.assertRaises(llm.LlmError):
            llm.web_search("x", max_fetches=3, timeout=5)

    def test_images_refused_without_allow_images(self):
        with self.assertRaises(llm.LlmError):
            llm.complete([llm.Message(role="user", content="u")], images=[b"png"])


class AnthropicTest(SearxTestCase):

    def setUp(self):
        super().setUp()
        self.patches = settings(backend="anthropic", api_key="sk-test")
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def test_defaults(self):
        self.assertTrue(llm.is_frontier())
        self.assertEqual(llm.model_name(), "claude-haiku-5-5")
        self.assertEqual(llm.model_label(), "claude-haiku-5-5, Anthropic")

    def test_schema_via_tool_use(self):
        seen = {}

        def fake_post(url, body, headers, timeout):  # pylint: disable=unused-argument
            seen.update(url=url, body=body, headers=headers)
            return backends.HttpReply(
                status=200,
                data={
                    "model": "claude-haiku-5-5",
                    "content": [{"type": "tool_use", "name": "reply", "input": {"a": 5}}],
                },
            )

        with mock.patch.object(anthropic_backend, "http_post", side_effect=fake_post):
            reply = llm.complete(
                [llm.Message(role="system", content="s"), llm.Message(role="user", content="u")], json_schema=SCHEMA
            )
        self.assertEqual(reply.data, {"a": 5})
        self.assertEqual(seen["url"], anthropic_backend.API_URL)
        self.assertEqual(seen["headers"]["x-api-key"], "sk-test")
        self.assertEqual(seen["body"]["system"], "s")
        self.assertEqual(seen["body"]["tool_choice"], {"type": "tool", "name": "reply"})
        self.assertEqual(seen["body"]["tools"][0]["input_schema"], SCHEMA)

    def test_web_search(self):
        data = {
            "model": "claude-haiku-5-5",
            "content": [
                {"type": "server_tool_use", "name": "web_search", "input": {"query": "x"}},
                {
                    "type": "web_search_tool_result",
                    "content": [
                        {"type": "web_search_result", "url": "https://a.example/p", "title": "A"},
                        {"type": "web_search_result", "url": "https://b.example/q", "title": "B"},
                    ],
                },
                {
                    "type": "text",
                    "text": "It is so.",
                    "citations": [{"type": "web_search_result_location", "url": "https://a.example/p", "title": "A"}],
                },
            ],
        }
        with mock.patch.object(
            anthropic_backend, "http_post", return_value=backends.HttpReply(status=200, data=data)
        ) as post:
            answer = llm.web_search("is it so", max_fetches=4, timeout=8)
        self.assertEqual(answer.text, "It is so.")
        self.assertEqual(answer.citations, [{"url": "https://a.example/p", "title": "A"}])
        self.assertEqual(answer.fetched, ["a.example", "b.example"])
        self.assertEqual(post.call_args[0][1]["tools"][0]["max_uses"], 4)

    def test_missing_key(self):
        patches = settings(backend="anthropic", api_key="")
        for p in self.patches:
            p.stop()
        with patches[0], patches[1], patches[2], mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(llm.LlmError):
                llm.complete([llm.Message(role="user", content="u")])
        for p in self.patches:
            p.start()


class OpenAITest(SearxTestCase):

    def test_web_search_parses_annotations(self):
        patches = settings(backend="openai", api_key="sk-test", model="gpt-5-mini")
        data = {
            "model": "gpt-5-mini",
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Answer.",
                            "annotations": [{"type": "url_citation", "url": "https://c.example/x", "title": "C"}],
                        }
                    ],
                },
            ],
        }
        with (
            patches[0],
            patches[1],
            patches[2],
            mock.patch.object(openai_backend, "http_post", return_value=backends.HttpReply(status=200, data=data)),
        ):
            answer = llm.web_search("q", max_fetches=6, timeout=8)
        self.assertEqual(answer.text, "Answer.")
        self.assertEqual(answer.citations, [{"url": "https://c.example/x", "title": "C"}])
        self.assertEqual(answer.fetched, ["c.example"])
