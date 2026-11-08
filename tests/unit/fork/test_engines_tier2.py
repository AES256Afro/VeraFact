# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import pathlib
import types
from unittest import mock
from urllib.parse import parse_qs, urlparse

import searx.engines
import searx.search
from searx.fork.result_types import ClaimReview
from searx.result_types import EngineResults, MainResult
from tests import SearxTestCase

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class PolitiFactTest(SearxTestCase):

    TEST_SETTINGS = "test_factcheck.yml"

    def setUp(self):
        super().setUp()
        self.engine = searx.engines.engines["politifact"]

    def tearDown(self):
        searx.search.load_engines([])

    def test_request(self):
        params = {}
        self.engine.request("moon landing", params)
        self.assertEqual(params["url"], "https://politifact.com/search/?q=moon+landing")

    def test_response(self):
        resp = mock.Mock()
        resp.text = (FIXTURES / "politifact_search.html").read_text()
        results = self.engine.response(resp)
        self.assertEqual(len(results), 2)
        first = results[0]
        self.assertIsInstance(first, ClaimReview)
        self.assertTrue(first.url.startswith("https://politifact.com/factchecks/2024/may/08/"))
        self.assertEqual(first.claim, "Video proves the moon landing was a hoax.")
        self.assertEqual(first.title, first.claim)
        self.assertEqual(first.claimant, "Viral image")
        self.assertEqual(first.claim_date, "2024-04-12")
        self.assertEqual(first.verdict_raw, "Pants on Fire!")
        self.assertEqual(first.reviewer, "PolitiFact")
        self.assertEqual(first.review_date, "2024-05-08")
        self.assertIn("Facebook post", first.content)
        first.normalize_result_fields()
        self.assertEqual(first.verdict, "false")

    def test_response_empty(self):
        resp = mock.Mock()
        resp.text = "<html><body><p>nothing</p></body></html>"
        self.assertEqual(len(self.engine.response(resp)), 0)

    def test_plain_articles_are_skipped(self):
        resp = mock.Mock()
        resp.text = (
            '<div class="py-4 border-bottom"><h5 class="pf-search-factcheck-title">'
            '<a href="https://politifact.com/article/2019/jul/18/apollo/">Fifty years after Apollo</a></h5></div>'
            '<div class="py-4 border-bottom"><h5 class="pf-search-factcheck-title">'
            '<a href="https://politifact.com/factchecks/2024/x/">A claim</a></h5></div>'
        )
        results = self.engine.response(resp)
        self.assertEqual([r.url for r in results], ["https://politifact.com/factchecks/2024/x/"])
        self.assertEqual(results[0].verdict, "unrated")


class WordPressTest(SearxTestCase):

    TEST_SETTINGS = "test_factcheck.yml"

    def setUp(self):
        super().setUp()
        self.engine = searx.engines.engines["factcheck.org"]

    def tearDown(self):
        searx.search.load_engines([])

    def test_request(self):
        params = {"pageno": 2}
        self.engine.request("moon landing", params)
        url = urlparse(params["url"])
        self.assertEqual(url.netloc, "www.factcheck.org")
        self.assertEqual(url.path, "/wp-json/wp/v2/search")
        q = parse_qs(url.query)
        self.assertEqual(q["search"], ["moon landing"])
        self.assertEqual(q["page"], ["2"])
        self.assertEqual(q["per_page"], ["20"])

    def test_response(self):
        resp = mock.Mock()
        resp.status_code = 200
        resp.json.return_value = [
            {
                "id": 1,
                "title": "Lunar Conspiracy Theorists: Come Back to Earth!",
                "url": "https://www.factcheck.org/2009/07/lunar/",
            },
            {"id": 2, "title": "Q&amp;A on the &#8216;moon&#8217;", "url": "https://www.factcheck.org/2020/01/q/"},
            {"id": 3, "title": "no url"},
            "junk",
        ]
        results = self.engine.response(resp)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].reviewer, "FactCheck.org")
        self.assertEqual(results[0].claim, "Lunar Conspiracy Theorists: Come Back to Earth!")
        self.assertEqual(results[0].verdict, "unrated")
        self.assertEqual(results[1].title, "Q&A on the ‘moon’")

    def test_response_past_last_page(self):
        resp = mock.Mock()
        resp.status_code = 400
        self.assertEqual(len(self.engine.response(resp)), 0)


class SiteScopedTest(SearxTestCase):

    TEST_SETTINGS = "test_factcheck.yml"

    def setUp(self):
        super().setUp()
        self.engine = searx.engines.engines["snopes"]
        self.engine._base = None  # pylint: disable=protected-access
        self.seen = {}

        def base_request(query, params):
            self.seen["query"] = query
            params["url"] = "https://base.example/?q=" + query

        def base_response(resp):  # pylint: disable=unused-argument
            res = EngineResults()
            res.add(MainResult(url="https://www.snopes.com/fact-check/moon/", title="Moon", content="c"))
            res.add(MainResult(url="https://example.com/not-snopes", title="x"))
            res.add({"url": "https://www.snopes.com/news/legacy/", "title": "Legacy", "content": ""})
            res.add({"url": "https://snopes.com.evil.example/", "title": "spoof"})
            return res

        self.fake = types.SimpleNamespace(request=base_request, response=base_response, name="fakebase")
        searx.engines.engines["fakebase"] = self.fake

    def tearDown(self):
        searx.engines.engines.pop("fakebase", None)
        searx.search.load_engines([])

    def test_request_scopes_the_query(self):
        params = {}
        self.engine.request("moon landing", params)
        self.assertEqual(self.seen["query"], "site:snopes.com moon landing")
        self.assertEqual(params["url"], "https://base.example/?q=site:snopes.com moon landing")

    def test_response_keeps_site_hits(self):
        results = self.engine.response(mock.Mock())
        self.assertEqual(
            [r.url for r in results], ["https://www.snopes.com/fact-check/moon/", "https://www.snopes.com/news/legacy/"]
        )
        self.assertIsInstance(results[0], ClaimReview)
        self.assertEqual(results[0].reviewer, "Snopes")
        self.assertEqual(results[0].claim, "Moon")
        self.assertEqual(results[0].verdict, "unrated")

    def test_setup_requires_site(self):
        with self.assertRaises(ValueError):
            self.engine.setup({"name": "x"})

    def test_private_copy_of_base(self):
        # demo_online is a real upstream engine module that is not registered in the test settings
        self.engine._base = None  # pylint: disable=protected-access
        with mock.patch.object(self.engine, "base_engine", "demo_online"):
            base = self.engine._resolve_base()  # pylint: disable=protected-access
            self.assertEqual(base.name, "vf demo online")
            self.assertTrue(callable(base.request))
            self.assertTrue(callable(base.response))
            self.assertNotIn("demo_online", searx.engines.engines)
        self.engine._base = None  # pylint: disable=protected-access

    def test_unknown_base_is_an_error(self):
        self.engine._base = None  # pylint: disable=protected-access
        with mock.patch.object(self.engine, "base_engine", "no_such_engine_xyz"):
            with self.assertRaises(ValueError):
                self.engine._resolve_base()  # pylint: disable=protected-access
        self.engine._base = None  # pylint: disable=protected-access
