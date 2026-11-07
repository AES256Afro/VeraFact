# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

from unittest import mock
from urllib.parse import parse_qs, urlparse

import searx.engines
import searx.search
from searx.fork.result_types import ClaimReview
from tests import SearxTestCase

FIXTURE = {
    "claims": [
        {
            "text": "The Eiffel Tower was sold for scrap in 1925.",
            "claimant": "Social media post",
            "claimDate": "2024-02-01T00:00:00Z",
            "claimReview": [
                {
                    "publisher": {"name": "Snopes", "site": "snopes.com"},
                    "url": "https://www.snopes.com/fact-check/eiffel-tower-scrap/",
                    "title": "Was the Eiffel Tower Sold for Scrap?",
                    "reviewDate": "2024-02-03T12:00:00Z",
                    "textualRating": "False",
                    "languageCode": "en",
                },
                {
                    "publisher": {"site": "leadstories.com"},
                    "url": "https://leadstories.com/eiffel.html",
                    "textualRating": "Satire",
                },
                {"publisher": {"name": "No URL"}, "textualRating": "False"},
            ],
        },
        "not a claim",
        {"text": "No reviews here"},
    ],
    "nextPageToken": "abc",
}


class GoogleFactCheckTest(SearxTestCase):

    TEST_SETTINGS = "test_factcheck.yml"

    def setUp(self):
        super().setUp()
        self.engine = searx.engines.engines["google fact check"]

    def tearDown(self):
        searx.search.load_engines([])

    def test_loaded_with_a_key(self):
        self.assertEqual(self.engine.api_key, "test-key")
        self.assertEqual(self.engine.categories, ["fact check"])

    def test_setup_without_key_declines(self):
        with mock.patch.object(self.engine, "get_setting", return_value=""):
            self.assertFalse(self.engine.setup({"name": "google fact check"}))

    def test_request(self):
        params = {"searxng_locale": "en-US"}
        self.engine.request("eiffel tower scrap", params)
        url = urlparse(params["url"])
        self.assertEqual(url.netloc, "factchecktools.googleapis.com")
        query = parse_qs(url.query)
        self.assertEqual(query["query"], ["eiffel tower scrap"])
        self.assertEqual(query["key"], ["test-key"])
        self.assertEqual(query["languageCode"], ["en"])
        self.assertEqual(query["pageSize"], ["20"])
        self.assertTrue(params["raise_for_httperror"])

    def test_request_without_locale(self):
        params = {"searxng_locale": "all"}
        self.engine.request("x", params)
        self.assertNotIn("languageCode", parse_qs(urlparse(params["url"]).query))

    def test_response(self):
        resp = mock.Mock()
        resp.json.return_value = FIXTURE
        results = self.engine.response(resp)
        self.assertEqual(len(results), 2)
        first, second = results
        self.assertIsInstance(first, ClaimReview)
        self.assertEqual(first.url, "https://www.snopes.com/fact-check/eiffel-tower-scrap/")
        self.assertEqual(first.title, "Was the Eiffel Tower Sold for Scrap?")
        self.assertEqual(first.claim, "The Eiffel Tower was sold for scrap in 1925.")
        self.assertEqual(first.claimant, "Social media post")
        self.assertEqual(first.claim_date, "2024-02-01")
        self.assertEqual(first.reviewer, "Snopes")
        self.assertEqual(first.review_date, "2024-02-03")
        self.assertEqual(first.verdict_raw, "False")
        self.assertEqual(first.publishedDate.year, 2024)
        first.normalize_result_fields()
        self.assertEqual(first.verdict, "false")
        # publisher without a name falls back to its site; title falls back to the claim
        self.assertEqual(second.reviewer, "leadstories.com")
        self.assertEqual(second.title, "The Eiffel Tower was sold for scrap in 1925.")
        second.normalize_result_fields()
        self.assertEqual(second.verdict, "satire")

    def test_response_empty(self):
        for payload in ({}, {"claims": []}, [], "x"):
            resp = mock.Mock()
            resp.json.return_value = payload
            self.assertEqual(len(self.engine.response(resp)), 0)
