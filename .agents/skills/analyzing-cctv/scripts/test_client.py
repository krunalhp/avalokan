"""Isolated tests for client.py using httpx.MockTransport (no server needed).

Run: python -m unittest discover -s .agents/skills/analyzing-cctv/scripts
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client  # noqa: E402

TOKEN = "s3cret-token-value"


def run(argv, handler, env=None):
    calls = []

    def record(req):
        calls.append(req)
        return handler(req)

    env = {"AVALOKAN_URL": "http://127.0.0.1:8000", **(env or {})}
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = client.main(argv, transport=httpx.MockTransport(record))
    return code, json.loads(out.getvalue()), err.getvalue(), calls


class ClientTests(unittest.TestCase):
    def test_token_sent_but_never_printed_and_demo_has_no_header(self):
        h = lambda r: httpx.Response(401, json={"detail": "bad"})
        code, out, err, calls = run(["capabilities"], h, {"AVALOKAN_API_TOKEN": TOKEN})
        self.assertEqual(code, client.EXIT_API)
        self.assertEqual(calls[0].headers["authorization"], f"Bearer {TOKEN}")
        self.assertNotIn(TOKEN, json.dumps(out) + err)
        _, _, _, calls = run(["capabilities"], lambda r: httpx.Response(200, json={}))
        self.assertNotIn("authorization", calls[0].headers)

    def test_rejects_credentials_in_url(self):
        code, out, _, calls = run(["capabilities"], None, {"AVALOKAN_URL": "http://u:p@h/?token=x"})
        self.assertEqual(code, client.EXIT_USAGE)
        self.assertEqual(calls, [])

    def test_submit_requires_allowlist_and_sends_idempotency_key(self):
        code, _, _, calls = run(["submit", "m1", "--idempotency-key", "k1"], None)
        self.assertEqual((code, calls), (client.EXIT_USAGE, []))
        h = lambda r: httpx.Response(202, json={"id": "j1", "status": "queued"})
        code, out, _, calls = run(
            ["submit", "m1", "--idempotency-key", "k1", "--deny-all", "--config", '{"sample_fps":5}'], h)
        self.assertEqual(code, 0)
        self.assertEqual(calls[0].headers["idempotency-key"], "k1")
        self.assertEqual(json.loads(calls[0].content),
                         {"media_id": "m1", "config": {"sample_fps": 5, "allowed_activities": []}})

    def test_mutations_require_authorization(self):
        code, _, _, calls = run(["review", "e1", "--verdict", "confirmed"], None)
        self.assertEqual((code, calls), (client.EXIT_USAGE, []))
        code, _, _, calls = run(["upload", "/nonexistent.mp4"], None)
        self.assertEqual((code, calls), (client.EXIT_USAGE, []))

    def test_review_network_error_not_retried(self):
        def h(r):
            raise httpx.ConnectError("boom")
        code, _, err, calls = run(["review", "e/1", "--verdict", "rejected", "--authorized"], h)
        self.assertEqual(code, client.EXIT_NETWORK)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url.raw_path, b"/v1/events/e%2F1/reviews")
        self.assertIn("Verify state", err)

    def test_upload_sends_basename_once(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "clip.mp4"
            f.write_bytes(b"data")

            def h(r):
                if r.url.path == "/v1/capabilities":
                    return httpx.Response(200, json={"max_upload_bytes": 100})
                return httpx.Response(201, json={"id": "m1"})
            code, out, _, calls = run(["upload", str(f), "--authorized"], h)
        self.assertEqual((code, out["id"]), (0, "m1"))
        posts = [c for c in calls if c.method == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertIn(b'filename="clip.mp4"', posts[0].content)
        self.assertNotIn(d.encode(), posts[0].content)

    def test_events_pagination_with_filters(self):
        def h(r):
            cur = r.url.params.get("cursor")
            self.assertEqual(r.url.params["activity"], "object.present")
            return httpx.Response(200, json={"items": [{"id": cur or "a"}],
                                             "next_cursor": None if cur else "b"})
        code, out, _, calls = run(["events", "j1", "--activity", "object.present", "--all"], h)
        self.assertEqual(code, 0)
        self.assertEqual([i["id"] for i in out["items"]], ["a", "b"])
        self.assertFalse(out["truncated"])

    def test_truncation_cursor_does_not_skip_unreturned_items(self):
        def h(r):
            start = int(r.url.params.get("cursor", "0"))
            end = min(10, start + int(r.url.params.get("limit", "100")))
            return httpx.Response(200, json={
                "items": [{"id": i} for i in range(start, end)],
                "next_cursor": str(end) if end < 10 else None,
            })
        code, out, _, _ = run(["events", "j1", "--all", "--max-items", "3"], h)
        self.assertEqual(code, 0)
        self.assertEqual(out["items"], [{"id": 0}, {"id": 1}, {"id": 2}])
        self.assertEqual(out["next_cursor"], "3")

    def test_wait_failed_job_is_nonzero(self):
        h = lambda r: httpx.Response(200, json={"id": "j1", "status": "failed", "error": "x"})
        code, out, _, _ = run(["wait", "j1"], h)
        self.assertEqual(code, client.EXIT_FAILED)
        self.assertEqual(out["error"]["data"]["status"], "failed")

    def test_wait_deadline(self):
        h = lambda r: httpx.Response(200, json={"id": "j1", "status": "running", "progress": 0.1})
        with mock.patch.object(client.time, "sleep", lambda s: None):
            code, _, _, _ = run(["wait", "j1", "--timeout", "0.01", "--interval", "0.5"], h)
        self.assertEqual(code, client.EXIT_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
