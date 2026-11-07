# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import searx.metrics
from searx.fork.result_types import ClaimReview
from searx.results import ResultContainer
from tests import SearxTestCase


class ClaimReviewTest(SearxTestCase):

    def test_defaults(self):
        r = ClaimReview(url="https://www.politifact.com/x/")
        self.assertEqual(r.template, "fork_claim_review.html")
        self.assertEqual(r.verdict, "unrated")
        self.assertEqual(r.claim, "")

    def test_normalise_fills_verdict(self):
        r = ClaimReview(
            url="https://www.politifact.com/x/",
            claim="  The  moon\nis cheese ",
            verdict_raw=" Pants  on Fire ",
            reviewer="PolitiFact",
        )
        r.normalize_result_fields()
        self.assertEqual(r.verdict, "false")
        self.assertEqual(r.claim, "The moon is cheese")
        self.assertEqual(r.verdict_raw, "Pants on Fire")
        self.assertEqual(r.parsed_url.netloc, "www.politifact.com")

    def test_engine_verdict_is_kept(self):
        r = ClaimReview(url="https://example.org/", verdict_raw="False", verdict="satire")
        r.normalize_result_fields()
        self.assertEqual(r.verdict, "satire")

    def test_container_keeps_result(self):
        searx.metrics.initialize(["google fact check"], enabled=False)
        rc = ResultContainer()
        rc.extend("google fact check", [ClaimReview(url="https://www.snopes.com/a/", title="A", verdict_raw="False")])
        rc.extend("google fact check", [ClaimReview(url="https://www.snopes.com/a/", title="A", verdict_raw="False")])
        results = rc.get_ordered_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].verdict, "false")
        self.assertIn("verdict", results[0].as_dict())
