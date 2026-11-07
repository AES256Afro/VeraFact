# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

from parameterized import parameterized

from searx.fork.factcheck import trigger
from tests import SearxTestCase


class AdaptFormTest(SearxTestCase):

    def test_passthrough(self):
        form = {"q": "moon landing", "category_general": "1", "language": "en"}
        self.assertEqual(trigger.adapt_form(form), form)

    def test_mode_factcheck_wins(self):
        out = trigger.adapt_form({"q": "x", "mode": "factcheck", "category_general": "1", "categories": "images,news"})
        self.assertEqual(out, {"q": "x", "category_fact check": "1"})

    def test_mode_search_drops_it(self):
        out = trigger.adapt_form({"q": "x", "mode": "search", "category_fact check": "1"})
        self.assertEqual(out, {"q": "x"})
        out = trigger.adapt_form({"q": "x", "mode": "search", "categories": "fact check,news"})
        self.assertEqual(out, {"q": "x", "categories": "news"})
        out = trigger.adapt_form({"q": "x", "mode": "search", "categories": "fact check"})
        self.assertEqual(out, {"q": "x"})

    @parameterized.expand(
        [
            ("!fc the moon is cheese", "the moon is cheese"),
            ("!factcheck the moon is cheese", "the moon is cheese"),
            ("the moon is cheese !fc", "the moon is cheese"),
            ("!FC the moon is cheese", "the moon is cheese"),
        ]
    )
    def test_bang(self, query, expected):
        out = trigger.adapt_form({"q": query, "category_general": "1"})
        self.assertEqual(out, {"q": expected, "category_fact check": "1"})

    def test_bang_alone_is_not_stripped(self):
        self.assertEqual(trigger.adapt_form({"q": "!fc"}), {"q": "!fc"})

    def test_bang_inside_is_kept(self):
        self.assertEqual(trigger.adapt_form({"q": "a !fc b"}), {"q": "a !fc b"})

    def test_mode_helpers(self):
        self.assertTrue(trigger.is_factcheck_mode(["fact check", "general"]))
        self.assertFalse(trigger.is_strict_mode(["fact check", "general"]))
        self.assertTrue(trigger.is_strict_mode(["fact check"]))
        self.assertFalse(trigger.is_factcheck_mode(["general"]))


class LooksLikeClaimTest(SearxTestCase):

    @parameterized.expand(
        [
            ("is it true that the moon landing was faked",),
            ("Is this true: vaccines contain microchips",),
            ("did Elvis really fake his death",),
            ("fact check: the eiffel tower was sold for scrap",),
            ("debunk 5g causes covid",),
            ('"The Eiffel Tower was sold for scrap in 1925"',),
            ("The president signed an order that bans all gas stoves in every home from next year.",),
        ]
    )
    def test_claims(self, query):
        self.assertTrue(trigger.looks_like_claim(query))

    @parameterized.expand(
        [
            ("",),
            ("python list comprehension",),
            ("weather berlin",),
            ("eiffel tower height",),
            ("how to fix a leaking tap",),
            ("best laptops 2026",),
            ("The quick brown fox jumps over the lazy dog near the river bank today",),  # no full stop
            ("one two three four five six seven eight nine ten eleven twelve.",),  # no verb
        ]
    )
    def test_not_claims(self, query):
        self.assertFalse(trigger.looks_like_claim(query))
