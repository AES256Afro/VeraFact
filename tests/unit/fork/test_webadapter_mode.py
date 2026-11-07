# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import searx.plugins
import searx.search
from searx.engines import engines
from searx.preferences import Preferences
from searx.webadapter import get_search_query_from_webapp
from tests import SearxTestCase


class ModeInWebadapterTest(SearxTestCase):

    TEST_SETTINGS = "test_factcheck.yml"

    def tearDown(self):
        searx.search.load_engines([])

    def query(self, form):
        preferences = Preferences(["simple"], ["general", "fact check"], engines, searx.plugins.STORAGE)
        search_query, _, _, _, _ = get_search_query_from_webapp(preferences, form)
        return search_query

    def test_mode_field(self):
        sq = self.query({"q": "the moon is cheese", "mode": "factcheck", "category_general": "1"})
        self.assertEqual(sq.query, "the moon is cheese")
        self.assertEqual(sq.categories, ["fact check"])
        self.assertEqual([e.name for e in sq.engineref_list], ["google fact check"])

    def test_bang(self):
        sq = self.query({"q": "!fc the moon is cheese"})
        self.assertEqual(sq.query, "the moon is cheese")
        self.assertEqual(sq.categories, ["fact check"])

    def test_category_field_still_works(self):
        sq = self.query({"q": "x", "category_fact check": "1"})
        self.assertEqual(sq.categories, ["fact check"])
