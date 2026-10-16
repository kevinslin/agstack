"""Fault injection for transport distinctions that HTTPS integration cannot induce reliably."""
from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError


class SitesTransportTest(unittest.TestCase):
    def test_failures_are_distinct_and_redacted(self):
        request = runpy.run_path(str(Path(__file__).resolve().parents[1] / "skills/agtask/scripts/agtask"))["sites_request"]
        secret = "DO_NOT_EXPOSE_SECRET"
        scenarios = [
            (TimeoutError(secret), None, "timed out"),
            (URLError(TimeoutError(secret)), None, "timed out"),
            (URLError(secret), None, "transport failed"),
            (HTTPError("https://example.invalid", 403, secret, {}, None), None, "HTTP 403"),
            (None, secret.encode(), "malformed JSON"),
            (None, b'"\xff' + secret.encode(), "invalid text encoding"),
        ]
        for failure, body, label in scenarios:
            with self.subTest(label=label, failure=type(failure).__name__):
                opener = MagicMock()
                opener.open.side_effect = failure
                opener.open.return_value.__enter__.return_value.read.return_value = body
                with patch.dict(request.__globals__, sites_credentials=lambda _: (secret, secret), build_opener=lambda _: opener):
                    with self.assertRaises(request.__globals__["TaskError"]) as caught:
                        request({"backend": {"sites": {"url": "https://example.invalid"}}}, "list", {})
                self.assertIn(label, str(caught.exception))
                self.assertNotIn(secret, str(caught.exception))
                self.assertEqual(opener.open.call_count, 1)
                self.assertEqual(opener.open.call_args.kwargs["timeout"], 30.0)

    def test_hook_budget_is_unchanged(self):
        request = runpy.run_path(str(Path(__file__).resolve().parents[1] / "skills/agtask/scripts/agtask"))["sites_request"]
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b"[]"
        with patch.dict(request.__globals__, sites_credentials=lambda _: ("fake", "fake"), build_opener=lambda _: opener):
            self.assertEqual(request({"backend": {"sites": {"url": "https://example.invalid"}}}, "list", {}, hook_mode=True), [])
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 1.25)


if __name__ == "__main__":
    unittest.main()
