# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import json
import pathlib
from unittest import mock

from searx.fork.factcheck import claimreview
from searx.fork.result_types import ClaimReview
from tests import SearxTestCase

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
LEADSTORIES = json.loads((FIXTURES / "leadstories_claimreview.json").read_text())


def page(*blocks):
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks)
    return f"<html><head>{scripts}</head><body></body></html>"


class ExtractTest(SearxTestCase):

    def test_finds_claim_review(self):
        found = claimreview.extract_claim_reviews(page({"@type": "NewsArticle"}, LEADSTORIES))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["claimReviewed"], LEADSTORIES["claimReviewed"])

    def test_graph_and_lists(self):
        found = claimreview.extract_claim_reviews(page({"@graph": [{"@type": "WebPage"}, LEADSTORIES]}, [LEADSTORIES]))
        self.assertEqual(len(found), 2)

    def test_tolerates_bad_json(self):
        html = (
            '<script type="application/ld+json">{not json</script><script type="application/ld+json"><!-- x -->'
            + json.dumps(LEADSTORIES)
            + "</script>"
        )
        self.assertEqual(len(claimreview.extract_claim_reviews(html)), 1)
        self.assertEqual(claimreview.extract_claim_reviews(""), [])
        self.assertEqual(claimreview.extract_claim_reviews("<html></html>"), [])


class FieldsTest(SearxTestCase):

    def test_leadstories(self):
        fields = claimreview.claim_review_fields(LEADSTORIES)
        self.assertEqual(fields["claim"], LEADSTORIES["claimReviewed"])
        self.assertEqual(fields["claimant"], "facebook.com")
        self.assertEqual(fields["claim_date"], "2026-11-06")
        self.assertEqual(fields["verdict_raw"], "AI Made It")
        self.assertEqual(fields["verdict"], "false")  # unknown words, numeric 1/5 decides
        self.assertEqual(fields["reviewer"], "Lead Stories LLC")
        self.assertEqual(fields["review_date"], "2026-11-06")

    def test_words_beat_numbers(self):
        data = {"reviewRating": {"alternateName": "Mostly True", "ratingValue": 1, "bestRating": 5, "worstRating": 1}}
        self.assertEqual(claimreview.claim_review_fields(data)["verdict"], "mostly-true")

    def test_reviewer_from_host(self):
        fields = claimreview.claim_review_fields({"claimReviewed": "x"}, "https://www.politifact.com/a/")
        self.assertEqual(fields["reviewer"], "PolitiFact")
        self.assertEqual(fields["verdict"], "unrated")


class EnrichTest(SearxTestCase):

    def setUp(self):
        super().setUp()
        self.store = {}
        self.cache_get = mock.patch.object(
            claimreview.CACHE, "get", side_effect=lambda k, default=None: self.store.get(k, default)
        )
        self.cache_set = mock.patch.object(
            claimreview.CACHE, "set", side_effect=lambda k, v, expire=None: self.store.__setitem__(k, v)
        )
        self.cache_get.start()
        self.cache_set.start()

    def tearDown(self):
        self.cache_get.stop()
        self.cache_set.stop()
        super().tearDown()

    def test_fills_and_caches(self):
        a = ClaimReview(url="https://leadstories.com/a", title="a")
        b = ClaimReview(url="https://leadstories.com/b", title="b")
        rated = ClaimReview(url="https://www.politifact.com/c", title="c", verdict_raw="False", verdict="false")
        calls = []

        def fetch(urls, timeout):
            calls.append((list(urls), timeout))
            return {urls[0]: page(LEADSTORIES), urls[1]: None}

        n = claimreview.enrich([rated, a, b], max_fetch=5, timeout=2.0, fetch=fetch)
        self.assertEqual(n, 1)
        self.assertEqual(calls, [([a.url, b.url], 2.0)])
        self.assertEqual(a.verdict, "false")
        self.assertEqual(a.verdict_raw, "AI Made It")
        self.assertEqual(a.claim, LEADSTORIES["claimReviewed"])
        self.assertEqual(a.title, "a")  # existing non-empty fields are kept
        self.assertEqual(b.verdict, "unrated")  # fetch failed: left alone, not cached
        self.assertIn(a.url, self.store)
        self.assertNotIn(b.url, self.store)

    def test_cache_hit_skips_fetch(self):
        self.store["https://leadstories.com/a"] = {"verdict": "satire", "verdict_raw": "Satire"}
        self.store["https://leadstories.com/none"] = {}
        a = ClaimReview(url="https://leadstories.com/a", title="a")
        none = ClaimReview(url="https://leadstories.com/none", title="n")
        fetch = mock.Mock(return_value={})
        n = claimreview.enrich([a, none], max_fetch=5, fetch=fetch)
        self.assertEqual(n, 1)
        self.assertEqual(a.verdict, "satire")
        self.assertEqual(none.verdict, "unrated")
        fetch.assert_not_called()

    def test_bounded(self):
        reviews = [ClaimReview(url=f"https://leadstories.com/{i}", title=str(i)) for i in range(10)]
        fetch = mock.Mock(return_value={})
        claimreview.enrich(reviews, max_fetch=3, fetch=fetch)
        self.assertEqual(len(fetch.call_args[0][0]), 3)
        fetch.reset_mock()
        self.assertEqual(claimreview.enrich(reviews, max_fetch=0, fetch=fetch), 0)
        fetch.assert_not_called()
