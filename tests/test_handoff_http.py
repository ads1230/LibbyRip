"""Local-only HTTP integration tests for the paired Libby handoff service.

All HTTP traffic goes to 127.0.0.1 and an ephemeral local port.
No request is ever made to Libby, OverDrive, or another external service.
"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import libby_handoff_server as handoff


ORIGIN = "chrome-extension://" + ("a" * 32)
LOAN = "https://libbyapp.com/open/loan/123456/987654"


class HandoffHttpTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.target = Path(self.work.name) / "loans.json"
        self.patch = patch.object(handoff, "LOANS_FILE", self.target)
        self.patch.start()
        self.addCleanup(self.patch.stop)

        self.secret = "test-only-pairing-secret-12345678"
        self.server = handoff.HandoffServer("127.0.0.1", 0, self.secret)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=3)

    def request(self, method, path, data=None, origin=ORIGIN, secret=None, content_type="application/json"):
        headers = {"Origin": origin}
        if secret is not None:
            headers["X-Libby-Handoff-Key"] = secret
        if content_type:
            headers["Content-Type"] = content_type
        payload = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data
        request = Request(self.base + path, data=payload, headers=headers, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, dict(response.headers), response.read()
        except HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_health_local_only(self):
        status, _, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_preflight_allows_extension_origin(self):
        status, headers, _ = self.request("OPTIONS", "/api/loan")
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertIn("X-Libby-Handoff-Key", headers["Access-Control-Allow-Headers"])

    def test_non_extension_origin_rejected(self):
        status, _, _ = self.request(
            "POST", "/api/loan", {"url": LOAN},
            origin="https://libbyapp.com", secret=self.secret
        )
        self.assertEqual(status, 403)
        self.assertFalse(self.target.exists())

    def test_pairing_key_required(self):
        for supplied in (None, "incorrect"):
            status, _, _ = self.request(
                "POST", "/api/loan", {"url": LOAN}, secret=supplied
            )
            self.assertEqual(status, 403)
        self.assertFalse(self.target.exists())

    def test_valid_handoff_persists_sanitised_data(self):
        data = {
            "url": LOAN + "?access_token=secret#chapter",
            "title": "  Example    Book  ",
            "author": "A. Author",
            "cookies": "never keep this"
        }
        status, _, body = self.request("POST", "/api/loan", data, secret=self.secret)
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)["saved"])
        saved = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["url"], LOAN)
        self.assertEqual(saved[0]["title"], "Example Book")
        self.assertNotIn("cookies", saved[0])
        self.assertNotIn("access_token", self.target.read_text(encoding="utf-8"))

    def test_same_loan_deduplicates(self):
        for title in ("One", "Two"):
            status, _, _ = self.request(
                "POST", "/api/loan", {"url": LOAN, "title": title},
                secret=self.secret
            )
            self.assertEqual(status, 201)
        saved = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["title"], "Two")

    def test_invalid_source_does_not_persist(self):
        status, _, _ = self.request(
            "POST", "/api/loan",
            {"url": "https://attacker.invalid/open/loan/123/456"},
            secret=self.secret
        )
        self.assertEqual(status, 400)
        self.assertFalse(self.target.exists())

    def test_rejects_oversize_body(self):
        status, _, _ = self.request(
            "POST", "/api/loan",
            {"url": LOAN, "title": "A" * 9000}, secret=self.secret
        )
        self.assertEqual(status, 413)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
