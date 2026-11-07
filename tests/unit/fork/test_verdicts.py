# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

from parameterized import parameterized

from searx.fork.factcheck import verdicts
from searx.fork.result_types import VERDICTS
from tests import SearxTestCase


class NormaliseTest(SearxTestCase):

    @parameterized.expand(
        [
            ("False", "false"),
            ("FALSE.", "false"),
            ("Pants on Fire!", "false"),
            ("Four Pinocchios", "false"),
            ("Not true", "false"),
            ("Untrue", "false"),
            ("No, the video is not from 2024", "false"),
            ("Mostly False", "mostly-false"),
            ("Three Pinocchios", "mostly-false"),
            ("Half True", "mixed"),
            ("Mixture", "mixed"),
            ("Two Pinocchios", "mixed"),
            ("Mostly True", "mostly-true"),
            ("Needs context", "mostly-true"),
            ("Not the Whole Story", "mostly-true"),
            ("True", "true"),
            ("Correct Attribution", "true"),
            ("Misleading", "misleading"),
            ("Miscaptioned", "misleading"),
            ("Missing Context", "misleading"),
            ("Full Flop", "misleading"),
            ("Unproven", "unproven"),
            ("Research In Progress", "unproven"),
            ("No evidence", "unproven"),
            ("Labeled Satire", "satire"),
            ("Outdated", "outdated"),
            ("Geppetto Checkmark", "true"),
            ("Falso", "false"),
            ("Falsch", "false"),
        ]
    )
    def test_known_ratings(self, raw, expected):
        self.assertEqual(verdicts.normalise(raw), expected)

    @parameterized.expand(
        [
            ("",),
            ("   ",),
            ("Rating 7",),
            ("Fact Crescendo",),
        ]
    )
    def test_unknown_stays_unrated(self, raw):
        self.assertEqual(verdicts.normalise(raw), "unrated")

    def test_longest_phrase_wins(self):
        self.assertEqual(verdicts.normalise("This claim is mostly false"), "mostly-false")
        self.assertEqual(verdicts.normalise("Verdict: untrue"), "false")
        self.assertEqual(verdicts.normalise("True, but needs context"), "mostly-true")

    def test_every_table_verdict_exists(self):
        for verdict in verdicts._DATA["verdicts"]:  # pylint: disable=protected-access
            self.assertIn(verdict, VERDICTS)

    @parameterized.expand(
        [
            (5, 5, 1, "true"),
            (4, 5, 1, "mostly-true"),
            (3, 5, 1, "mixed"),
            (2, 5, 1, "mostly-false"),
            (1, 5, 1, "false"),
            ("1", "1", "5", "true"),  # reversed scale, strings
            (0, 0, 0, "unrated"),
            (None, 5, 1, "unrated"),
            ("x", 5, 1, "unrated"),
        ]
    )
    def test_numeric_ratings(self, value, best, worst, expected):
        self.assertEqual(verdicts.normalise_rating(value, best, worst), expected)

    def test_severity_harshest_first(self):
        ranked = sorted(VERDICTS, key=verdicts.severity)
        self.assertEqual(ranked[0], "false")
        self.assertEqual(ranked[-1], "unrated")
        self.assertLess(verdicts.severity("false"), verdicts.severity("mixed"))
        self.assertLess(verdicts.severity("mixed"), verdicts.severity("true"))


class ReviewersTest(SearxTestCase):

    def test_known_hosts(self):
        self.assertEqual(verdicts.reviewer_name("www.politifact.com"), "PolitiFact")
        self.assertEqual(verdicts.reviewer_name("https://www.snopes.com/fact-check/x/"), "Snopes")
        self.assertEqual(verdicts.reviewer_name("factcheck.afp.com"), "AFP Fact Check")
        self.assertEqual(verdicts.reviewer_name("en.factcheck.afp.com"), "AFP Fact Check")
        self.assertTrue(verdicts.is_reviewer_host("fullfact.org"))

    def test_unknown_hosts(self):
        self.assertEqual(verdicts.reviewer_name("example.com"), "")
        self.assertFalse(verdicts.is_reviewer_host("https://example.com/politifact.com"))
        self.assertFalse(verdicts.is_reviewer_host(""))
