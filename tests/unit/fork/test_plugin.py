# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

from unittest.mock import Mock

import babel

import searx.metrics
import searx.plugins
import searx.results
from searx.extended_types import sxng_request
from searx.fork.factcheck.plugin import SXNGPlugin, cluster_claims, normalise_claim
from searx.fork.result_types import ClaimReview, FactCheckOffer, FactCheckSummary
from searx.result_types import Answer, MainResult
from tests import SearxTestCase


def review(url, claim, verdict_raw, reviewer):
    r = ClaimReview(url=url, title=claim, claim=claim, verdict_raw=verdict_raw, reviewer=reviewer)
    r.normalize_result_fields()
    return r


def search_mock(query, categories, pageno=1):
    sq = Mock(query=query, pageno=pageno, locale=babel.Locale.parse("en-US", sep="-"))
    sq.categories = categories
    return Mock(search_query=sq, user_plugins=["factcheck"], result_container=searx.results.ResultContainer())


class ClusterTest(SearxTestCase):

    def test_normalise_claim(self):
        self.assertEqual(normalise_claim("The Moon is made of cheese!"), frozenset({"moon", "made", "cheese"}))

    def test_cluster_near_duplicates(self):
        a = review("https://www.snopes.com/a", "The moon is made of green cheese", "False", "Snopes")
        b = review("https://www.politifact.com/b", "Moon made of green cheese", "Pants on Fire", "PolitiFact")
        c = review("https://fullfact.org/c", "The Eiffel Tower was sold for scrap", "False", "Full Fact")
        clusters = cluster_claims([c, a, b])
        self.assertEqual(len(clusters), 2)
        self.assertEqual({m.reviewer for m in clusters[0]}, {"Snopes", "PolitiFact"})
        self.assertEqual(clusters[1], [c])


class PluginTest(SearxTestCase):

    def setUp(self):
        super().setUp()
        searx.metrics.initialize([], enabled=False)
        self.storage = searx.plugins.PluginStorage()
        self.storage.load_settings({"searx.fork.factcheck.plugin.SXNGPlugin": {"active": True}})
        self.plugin = next(iter(self.storage))

    def test_is_registered_in_settings(self):
        self.assertIsInstance(self.plugin, SXNGPlugin)
        self.assertIn("searx.fork.factcheck.plugin.SXNGPlugin", searx.get_setting("plugins"))

    def test_strict_keeps_reviewers(self):
        search = search_mock("x", ["fact check"])
        keep = review("https://www.snopes.com/a", "a", "False", "Snopes")
        other = MainResult(url="https://example.com/a", title="a")
        reviewer_page = MainResult(url="https://www.politifact.com/x/", title="a")
        self.assertTrue(self.plugin.on_result(sxng_request, search, keep))
        self.assertFalse(self.plugin.on_result(sxng_request, search, other))
        self.assertTrue(self.plugin.on_result(sxng_request, search, reviewer_page))
        self.assertTrue(self.plugin.on_result(sxng_request, search, Answer(answer="x")))

    def test_mixed_keeps_everything(self):
        search = search_mock("x", ["fact check", "general"])
        self.assertTrue(self.plugin.on_result(sxng_request, search, MainResult(url="https://example.com/", title="a")))

    def test_offer_on_claim_like_search(self):
        with self.app.test_request_context("/search"):
            search = search_mock("is it true that the moon is cheese", ["general"])
            results = self.plugin.post_search(sxng_request, search)
            self.assertEqual(len(results), 1)
            offer = results[0]
            self.assertIsInstance(offer, FactCheckOffer)
            self.assertIn("mode=factcheck", offer.url)
            self.assertIn("q=is+it+true", offer.url)

    def test_no_offer_on_plain_search(self):
        with self.app.test_request_context("/search"):
            search = search_mock("python tutorial", ["general"])
            self.assertEqual(len(self.plugin.post_search(sxng_request, search)), 0)
            search = search_mock("is it true that the moon is cheese", ["general"], pageno=2)
            self.assertEqual(len(self.plugin.post_search(sxng_request, search)), 0)

    def test_summary_and_priority(self):
        with self.app.test_request_context("/search"):
            search = search_mock("moon cheese", ["fact check"])
            rc = search.result_container
            rc.extend(
                "a",
                [
                    review("https://www.snopes.com/a", "The moon is made of cheese", "False", "Snopes"),
                    review("https://www.politifact.com/b", "Moon is made of cheese", "Pants on Fire", "PolitiFact"),
                    review("https://fullfact.org/c", "The moon is made of cheese", "Mostly False", "Full Fact"),
                    review(
                        "https://leadstories.com/d", "The Eiffel Tower was sold for scrap", "Satire", "Lead Stories"
                    ),
                ],
            )
            results = self.plugin.post_search(sxng_request, search)
            self.assertEqual(len(results), 1)
            summary = results[0]
            self.assertIsInstance(summary, FactCheckSummary)
            self.assertEqual(summary.reviews, 4)
            self.assertEqual(summary.reviewers, 4)
            self.assertEqual(summary.claims, 2)
            self.assertEqual(summary.counts, [("false", 2), ("mostly-false", 1), ("satire", 1)])
            self.assertIn("mode=search", summary.url)
            priorities = {r.reviewer: r.priority for r in rc.main_results_map.values()}
            self.assertEqual(priorities["Snopes"], "high")
            self.assertEqual(priorities["Lead Stories"], "")

    def test_summary_with_no_reviews(self):
        with self.app.test_request_context("/search"):
            search = search_mock("something nobody checked", ["fact check"])
            results = self.plugin.post_search(sxng_request, search)
            summary = results[0]
            self.assertEqual(summary.reviews, 0)
            self.assertEqual(summary.counts, [])
