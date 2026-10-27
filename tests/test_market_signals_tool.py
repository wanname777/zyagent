from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from typing import Dict

from zyagent.adapters.tools.market_signals import MarketSignalsTool


class FakeRequester:
    def __init__(self, fail_source: str = "") -> None:
        self.fail_source = fail_source
        self.urls = []

    def __call__(
        self,
        url: str,
        headers: Dict[str, str],
        timeout: float,
    ) -> bytes:
        self.urls.append(url)
        if self.fail_source and self.fail_source in url:
            raise RuntimeError("source unavailable")
        if "hn.algolia.com" in url:
            return json.dumps(
                {
                    "hits": [
                        {
                            "objectID": "123",
                            "title": "Looking for an AI lead follow-up alternative",
                            "url": "https://example.com/hn-item",
                            "created_at": "2026-10-20T12:00:00Z",
                            "points": 42,
                            "num_comments": 18,
                            "story_text": "Our current workflow is expensive and difficult.",
                        }
                    ]
                }
            ).encode()
        if "api.github.com" in url:
            return json.dumps(
                {
                    "items": [
                        {
                            "html_url": "https://github.com/acme/agent/issues/7",
                            "title": "Need pricing controls for customer workflows",
                            "created_at": "2026-10-19T10:00:00Z",
                            "comments": 11,
                            "body": "Customers need a spending limit before they pay.",
                            "repository_url": "https://api.github.com/repos/acme/agent",
                            "reactions": {"total_count": 8},
                        }
                    ]
                }
            ).encode()
        if "news.google.com" in url:
            return b"""<?xml version="1.0" encoding="UTF-8"?>
            <rss><channel><item>
              <title>Small businesses test AI receptionists</title>
              <link>https://example.com/news-item</link>
              <pubDate>Sun, 18 Oct 2026 08:00:00 GMT</pubDate>
              <description>Teams compare cost and revenue impact.</description>
              <source>Example News</source>
            </item></channel></rss>"""
        raise AssertionError(f"Unexpected URL: {url}")


class MarketSignalsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = lambda: datetime(2026, 10, 27, tzinfo=timezone.utc)

    def test_collects_and_ranks_public_market_signals(self) -> None:
        requester = FakeRequester()
        tool = MarketSignalsTool(requester=requester, now_provider=self.now)

        payload = json.loads(
            tool.execute(
                {
                    "query": "AI agent for small business",
                    "days": 30,
                    "limit": 5,
                }
            )
        )

        self.assertEqual(payload["query"], "AI agent for small business")
        self.assertEqual(payload["window_days"], 30)
        self.assertEqual(
            set(payload["source_status"]),
            {"hacker_news", "github", "google_news"},
        )
        self.assertTrue(
            all(value == "ok" for value in payload["source_status"].values())
        )
        self.assertEqual(len(payload["items"]), 3)
        self.assertIn("buying", payload["items"][0]["signal_tags"])
        self.assertEqual(payload["items"][0]["source"], "hacker_news")
        self.assertEqual(len(requester.urls), 3)

    def test_keeps_partial_results_when_one_source_fails(self) -> None:
        tool = MarketSignalsTool(
            requester=FakeRequester(fail_source="api.github.com"),
            now_provider=self.now,
        )

        payload = json.loads(
            tool.execute({"query": "AI assistant", "days": 14, "limit": 3})
        )

        self.assertEqual(payload["source_status"]["github"], "error")
        self.assertEqual(len(payload["items"]), 2)
        self.assertTrue(any(error["source"] == "github" for error in payload["errors"]))

    def test_validates_arguments(self) -> None:
        tool = MarketSignalsTool(
            requester=FakeRequester(),
            now_provider=self.now,
        )

        with self.assertRaises(ValueError):
            tool.execute({"query": "", "days": 30})
        with self.assertRaises(ValueError):
            tool.execute({"query": "test", "days": 0})
        with self.assertRaises(ValueError):
            tool.execute({"query": "test", "limit": 100})


if __name__ == "__main__":
    unittest.main()
