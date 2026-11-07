# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import os
from unittest import mock

import msgspec

from searx import settings
from searx.fork.settings import SettingsFork
from tests import SearxTestCase


def decode(cfg: dict, environ: dict[str, str] | None = None) -> SettingsFork:
    """Decode ``cfg`` the way searx.settings_defaults.apply_schema does."""
    with mock.patch.dict(os.environ, environ or {}, clear=True):
        return msgspec.json.decode(msgspec.json.encode(cfg), type=SettingsFork)


class ForkSettingsTest(SearxTestCase):

    def test_loaded_settings_have_fork(self):
        fork = settings["fork"]
        self.assertIsInstance(fork, SettingsFork)
        self.assertEqual(fork.llm.backend, "disabled")
        self.assertTrue(fork.factcheck.enabled)
        self.assertFalse(fork.ocr.enabled)
        self.assertEqual(fork.appearance.look, "default")
        self.assertEqual(fork.appearance.mark, "grid-check")
        self.assertEqual(fork.appearance.wordmark, "two-tone")

    def test_brand_sweep(self):
        self.assertEqual(settings["general"]["instance_name"], "VeraFact")
        self.assertIn("fact check", settings["categories_as_tabs"])

    def test_defaults_match_the_plan(self):
        fork = decode({})
        self.assertEqual(fork.llm.timeout, 20)
        self.assertEqual(fork.llm.max_tokens, 400)
        self.assertFalse(fork.llm.allow_images)
        self.assertFalse(fork.llm.search_assist)
        self.assertEqual(fork.llm.search_assist_max_fetches, 6)
        self.assertEqual(fork.ocr.backend, "tesseract_http")
        self.assertEqual(fork.ocr.languages, ["eng"])
        self.assertEqual(fork.factcheck.enrich_top, 5)
        self.assertTrue(fork.modelfit.enabled)

    def test_yaml_values_are_applied(self):
        fork = decode({"llm": {"backend": "openai_compat", "base_url": "http://ollama:11434/v1", "timeout": 5}})
        self.assertEqual(fork.llm.backend, "openai_compat")
        self.assertEqual(fork.llm.base_url, "http://ollama:11434/v1")
        self.assertEqual(fork.llm.timeout, 5)

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(msgspec.ValidationError):
            decode({"llm": {"bogus": 1}})
        with self.assertRaises(msgspec.ValidationError):
            decode({"spam": {}})

    def test_bad_value_is_rejected(self):
        with self.assertRaises(msgspec.ValidationError):
            decode({"llm": {"backend": "skynet"}})
        with self.assertRaises(msgspec.ValidationError):
            decode({"appearance": {"mark": "swoosh"}})
        with self.assertRaises(msgspec.ValidationError):
            decode({"llm": {"timeout": "soon"}})

    def test_environment_overrides_yaml(self):
        fork = decode(
            {"llm": {"backend": "disabled", "model": "from-yaml"}},
            {
                "FORK_LLM_BACKEND": "anthropic",
                "FORK_LLM_MODEL": "from-env",
                "FORK_LLM_API_KEY": "sk-test",
                "FORK_OCR_URL": "http://127.0.0.1:8884",
                "FORK_FACTCHECK_GOOGLE_API_KEY": "g-test",
            },
        )
        self.assertEqual(fork.llm.backend, "anthropic")
        self.assertEqual(fork.llm.model, "from-env")
        self.assertEqual(fork.llm.api_key, "sk-test")
        self.assertEqual(fork.ocr.url, "http://127.0.0.1:8884")
        self.assertEqual(fork.factcheck.google_api_key, "g-test")

    def test_env_value_is_validated(self):
        with self.assertRaises(msgspec.ValidationError) as ctx:
            decode({}, {"FORK_LLM_BACKEND": "skynet"})
        self.assertIn("FORK_LLM_BACKEND", str(ctx.exception))

    def test_unrelated_env_is_ignored(self):
        fork = decode({}, {"FORK_LLM_TIMEOUT": "1", "SEARXNG_SECRET": "x"})
        self.assertEqual(fork.llm.timeout, 20)
