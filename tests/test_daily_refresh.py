import unittest
import urllib.error
from unittest import mock

from scripts import daily_refresh


def forbidden():
    return urllib.error.HTTPError("https://web.joongna.com/product/1", 403, "Forbidden", {}, None)


class DetailFetcherTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(daily_refresh, "BLOCKED_COOLDOWN_SECONDS", 0),
            mock.patch.object(daily_refresh, "REQUEST_DELAY_SECONDS", 0),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_retries_after_block(self):
        calls = iter([forbidden(), "본문"])

        def fake(_):
            value = next(calls)
            if isinstance(value, Exception):
                raise value
            return value

        with mock.patch.object(daily_refresh, "joongna_description", fake):
            fetcher = daily_refresh.DetailFetcher()
            self.assertEqual(fetcher.fetch_all([("joongna", "1")]), {("joongna", "1"): "본문"})
            self.assertEqual(fetcher.blocked["joongna"], 1)

    def test_gives_up_marketplace_and_leaves_unread_out(self):
        def always_blocked(_):
            raise forbidden()

        with mock.patch.object(daily_refresh, "joongna_description", always_blocked), \
                mock.patch.object(daily_refresh, "bunjang_description", lambda _: "번장 본문"):
            fetcher = daily_refresh.DetailFetcher()
            keys = [("joongna", str(index)) for index in range(daily_refresh.BLOCKED_GIVE_UP + 10)] + [("bunjang", "9")]
            results = fetcher.fetch_all(keys)
        self.assertEqual(results, {("bunjang", "9"): "번장 본문"})
        self.assertEqual(fetcher.blocked["joongna"], daily_refresh.BLOCKED_GIVE_UP)
