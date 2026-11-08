# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

from unittest import mock

from searx.fork import llm
from searx.fork.factcheck import llm_verdict
from searx.fork.result_types import ClaimReview
from tests import SearxTestCase


def review(url, claim, verdict_raw, reviewer, verdict=None):
    r = ClaimReview(url=url, title=claim, claim=claim, verdict_raw=verdict_raw, reviewer=reviewer)
    r.normalize_result_fields()
    if verdict:
        r.verdict = verdict
    return r


SOURCES = [
    review("https://www.snopes.com/a", "The moon is cheese", "False", "Snopes"),
    review("https://www.politifact.com/b", "Moon made of cheese", "Mostly False", "PolitiFact"),
    review("https://fullfact.org/c", "Moon cheese", "", "Full Fact"),  # unrated
]


class PromptTest(SearxTestCase):

    def test_messages_number_the_sources(self):
        messages = llm_verdict.build_messages("the moon is cheese", SOURCES)
        self.assertEqual(messages[0].role, "system")
        user = messages[1].content
        self.assertIn("Claim to assess:\nthe moon is cheese", user)
        self.assertIn("[1] Snopes\nrating: False", user)
        self.assertIn("[2] PolitiFact\nrating: Mostly False", user)
        self.assertIn("[3] Full Fact\nrating: not given", user)
        self.assertIn("url: https://fullfact.org/c", user)


class ValidateTest(SearxTestCase):

    def test_good(self):
        data = {"verdict": "false", "confidence": "high", "summary": "No.", "citations": [1, 2], "caveat": ""}
        self.assertEqual(llm_verdict.validate(data, SOURCES), "")

    def test_milder_than_sources_is_fine(self):
        data = {"verdict": "mixed", "confidence": "low", "summary": "Unclear.", "citations": [1], "caveat": ""}
        self.assertEqual(llm_verdict.validate(data, SOURCES), "")

    def test_no_citations(self):
        data = {"verdict": "false", "confidence": "high", "summary": "No.", "citations": [], "caveat": ""}
        self.assertIn("citation", llm_verdict.validate(data, SOURCES))

    def test_bad_citation_index(self):
        data = {"verdict": "false", "confidence": "high", "summary": "No.", "citations": [9], "caveat": ""}
        self.assertIn("not a source number", llm_verdict.validate(data, SOURCES))
        data["citations"] = [True]
        self.assertIn("not a source number", llm_verdict.validate(data, SOURCES))

    def test_stronger_than_cited_sources(self):
        data = {"verdict": "false", "confidence": "high", "summary": "No.", "citations": [2], "caveat": ""}
        self.assertIn("more certain", llm_verdict.validate(data, SOURCES))
        data = {"verdict": "false", "confidence": "high", "summary": "No.", "citations": [3], "caveat": ""}
        self.assertIn("more certain", llm_verdict.validate(data, SOURCES))

    def test_flipped_direction(self):
        data = {"verdict": "true", "confidence": "high", "summary": "Yes.", "citations": [1, 2], "caveat": ""}
        self.assertIn("other way", llm_verdict.validate(data, SOURCES))

    def test_unknown_values(self):
        self.assertIn("verdict", llm_verdict.validate({"verdict": "yes"}, SOURCES))
        self.assertIn("confidence", llm_verdict.validate({"verdict": "false", "confidence": "sure"}, SOURCES))
        self.assertIn(
            "summary", llm_verdict.validate({"verdict": "false", "confidence": "low", "summary": " "}, SOURCES)
        )


class RequestVerdictTest(SearxTestCase):

    def test_no_sources_means_no_call(self):
        with mock.patch("searx.fork.factcheck.llm_verdict.complete") as complete:
            answer = llm_verdict.request_verdict("x", [])
        complete.assert_not_called()
        self.assertFalse(answer.available)
        self.assertEqual(answer.reason, "no sources")

    def test_good_reply(self):
        reply = llm.Completion(
            text="{}",
            data={
                "verdict": "false",
                "confidence": "high",
                "summary": "The moon  is rock.",
                "citations": [2, 1],
                "caveat": "Cheese jokes aside.",
            },
            latency_ms=321,
        )
        with (
            mock.patch("searx.fork.factcheck.llm_verdict.complete", return_value=reply) as complete,
            mock.patch("searx.fork.factcheck.llm_verdict.model_label", return_value="qwen2.5:3b, local"),
        ):
            answer = llm_verdict.request_verdict("the moon is cheese", SOURCES)
        self.assertTrue(answer.available)
        self.assertEqual(answer.verdict, "false")
        self.assertEqual(answer.summary, "The moon is rock.")
        self.assertEqual(answer.caveat, "Cheese jokes aside.")
        self.assertEqual([c["index"] for c in answer.citations], ["1", "2"])
        self.assertEqual(answer.citations[0]["reviewer"], "Snopes")
        self.assertEqual(answer.model_label, "qwen2.5:3b, local")
        self.assertEqual(answer.latency_ms, 321)
        self.assertEqual(complete.call_args.kwargs["json_schema"], llm_verdict.SCHEMA)

    def test_invalid_reply_is_discarded(self):
        reply = llm.Completion(
            text="{}", data={"verdict": "true", "confidence": "high", "summary": "Yes.", "citations": [1], "caveat": ""}
        )
        with mock.patch("searx.fork.factcheck.llm_verdict.complete", return_value=reply):
            answer = llm_verdict.request_verdict("x", SOURCES)
        self.assertFalse(answer.available)
        self.assertIn("source check", answer.reason)

    def test_model_error(self):
        with mock.patch("searx.fork.factcheck.llm_verdict.complete", side_effect=llm.LlmError("down")):
            answer = llm_verdict.request_verdict("x", SOURCES)
        self.assertFalse(answer.available)
        self.assertEqual(answer.reason, "the model did not answer")
