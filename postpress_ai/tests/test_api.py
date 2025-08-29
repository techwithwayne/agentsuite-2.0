# =======================================
# ~/agentsuite/postpress_ai/tests/test_api.py
# =======================================
"""
CHANGE LOG
- 2025-08-15 — Add focused tests for the PostPress AI wrappers and diagnostics.
  * /version/ endpoint existence + shape
  * /health/ probe behavior (200 + 403) with Cloudflare-friendly semantics
  * /store/ normalization (target_used fallback + wp_status HTTP fallback)
  * /store/ non-JSON legacy response handled safely
  * Auth logging does NOT leak the raw shared key (masking hygiene)
- 2025-08-15 — # CHANGED: Ensure the legacy submodule is explicitly imported for patching.
  RATIONALE: The wrapper imports `from . import store_post_legacy` lazily. Our
  tests must import `postpress_ai.views.store_post_legacy` before patching, so
  `postpress_ai.views` exposes the `store_post_legacy` attribute. We now patch
  the submodule directly instead of accessing `ppa_views.store_post_legacy`.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Optional
from urllib.error import HTTPError

from django.test import TestCase, Client, override_settings
from django.http import JsonResponse, HttpResponse

# Absolute import of the package views is intentional (single source of truth)
from postpress_ai import views as ppa_views

# CHANGED: importlib used to ensure the legacy submodule is loaded and patchable
import importlib  # CHANGED


# ---------- Helpers for mocking ----------

class _DummyHTTPResponse:
    """Minimal object to mimic urlopen() return with a .status attribute."""
    def __init__(self, status: int = 200):
        self.status = status


def _make_http_error(url: str, code: int) -> HTTPError:
    """Construct an HTTPError suitable for raising from a mocked urlopen."""
    return HTTPError(url, code, f"HTTP {code}", hdrs=None, fp=None)


# ---------- Tests ----------

@override_settings(
    # Make sure our host is allowed in the Django test client context.
    ALLOWED_HOSTS=["testserver", "apps.techwithwayne.com"],
    # Provide deterministic settings consumed by the wrappers.
    PPA_SHARED_KEY="UNIT TEST KEY",
    PPA_WP_API_URL="https://example.com/wp-json/wp/v2",
)
class VersionAndHealthTests(TestCase):
    """Covers /version/ and /health/ endpoint behaviors (no external I/O)."""

    def setUp(self):
        # Use the same host we recommend for shell tests to avoid DisallowedHost.
        self.client = Client(
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
        )

    def test_version_endpoint_exists_and_shapes(self):
        """GET /postpress-ai/version/ returns expected keys and values."""
        r = self.client.get("/postpress-ai/version/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/json", r["Content-Type"].lower())

        data = json.loads(r.content.decode() or "{}")
        # Contract: ok/ver/build_time/module/file/ver present
        self.assertTrue(data.get("ok"))
        self.assertIsInstance(data.get("ver"), str)
        self.assertTrue(data.get("ver").startswith("postpress-ai."))
        self.assertIsInstance(data.get("build_time"), str)
        self.assertEqual(data.get("module"), "postpress_ai.views")
        self.assertIn("/postpress_ai/views/__init__.py", data.get("file", ""))
        self.assertEqual(data.get("ver"), ppa_views.VERSION)  # stable

    def test_health_probe_200_counts_as_reachable_and_allowed(self):
        """Mock urlopen→200; expect wp_reachable=True, wp_allowed=True, status=200."""
        # Monkeypatch postpress_ai.views.urlopen to return a dummy 200 response.
        def _fake_urlopen(req, timeout: float):  # signature-compatible
            return _DummyHTTPResponse(status=200)

        orig_urlopen = ppa_views.urlopen
        try:
            ppa_views.urlopen = _fake_urlopen  # patch
            r = self.client.get("/postpress-ai/health/", secure=True)
        finally:
            ppa_views.urlopen = orig_urlopen  # unpatch

        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode() or "{}")
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("wp_status"), 200)
        self.assertTrue(data.get("wp_reachable"))  # any HTTP status is reachable
        self.assertTrue(data.get("wp_allowed"))    # 200 is allowed
        self.assertEqual(data.get("module"), "postpress_ai.views")

    def test_health_probe_403_counts_as_reachable_but_not_allowed(self):
        """Mock urlopen raising HTTPError(403); reachable=True, allowed=False, status=403."""
        def _fake_urlopen(req, timeout: float):
            raise _make_http_error(url="https://example.com/wp-json/wp/v2", code=403)

        orig_urlopen = ppa_views.urlopen
        try:
            ppa_views.urlopen = _fake_urlopen  # patch
            r = self.client.get("/postpress-ai/health/", secure=True)
        finally:
            ppa_views.urlopen = orig_urlopen  # unpatch

        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode() or "{}")
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("wp_status"), 403)
        self.assertTrue(data.get("wp_reachable"))   # we got an HTTP status
        self.assertFalse(data.get("wp_allowed"))    # 403 is not allowed
        self.assertEqual(data.get("wp_error"), "http-error")
        self.assertIsInstance(data.get("ua_used"), str)
        self.assertIn("Mozilla/5.0", data.get("ua_used", ""))  # browser-like UA


@override_settings(
    ALLOWED_HOSTS=["testserver", "apps.techwithwayne.com"],
    PPA_SHARED_KEY="UNIT TEST KEY",
)
class StoreWrapperTests(TestCase):
    """Covers store normalization behavior and non-JSON handling."""

    def setUp(self):
        self.client = Client(
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
            HTTP_X_PPA_KEY="UNIT TEST KEY",  # correct key so auth=match True
        )

    def test_store_normalizes_target_and_wp_status_from_http_code(self):
        """
        Legacy returns JSON missing 'wp_status' and with 'target' mistakenly set to the WP API URL.
        Wrapper must:
          - Treat as stored=True when id/wp_id is present,
          - Fallback 'target_used' to the originally requested target ('draft'),
          - Fallback 'wp_status' to the HTTP status code (200).
        """
        # Fake legacy handler: return a JsonResponse body with id but no wp_status, and target as URL.
        legacy_body = {"ok": True, "id": 123, "target": "https://tech.site/wp-json/wp/v2"}
        legacy_json_response = JsonResponse(legacy_body, status=200)

        # CHANGED: Import the legacy submodule explicitly and patch there.
        legacy_mod = importlib.import_module("postpress_ai.views.store_post_legacy")  # CHANGED
        orig_store = legacy_mod.store_post  # CHANGED
        try:
            legacy_mod.store_post = lambda request: legacy_json_response  # CHANGED
            r = self.client.post(
                "/postpress-ai/store/",
                data=json.dumps({"title": "X", "content": "<p>Body</p>", "target": "draft"}),
                content_type="application/json",
                secure=True,
            )
        finally:
            legacy_mod.store_post = orig_store  # CHANGED

        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode() or "{}")
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("stored"))
        self.assertEqual(data.get("id"), 123)
        self.assertEqual(data.get("mode"), "created")
        self.assertEqual(data.get("target_used"), "draft")  # fallback from URL → requested target
        self.assertEqual(data.get("wp_status"), 200)        # fallback to HTTP status
        self.assertIn("ver", data)

    def test_store_returns_safe_failure_on_non_json_legacy(self):
        """
        If legacy returns an HttpResponse with non-JSON content,
        wrapper should return a normalized failure envelope (stored:false),
        with wp_status 'non-json' and a trimmed body message.
        """
        legacy_plain = HttpResponse("Not JSON", status=502, content_type="text/plain")

        # CHANGED: Import the legacy submodule explicitly and patch there.
        legacy_mod = importlib.import_module("postpress_ai.views.store_post_legacy")  # CHANGED
        orig_store = legacy_mod.store_post  # CHANGED
        try:
            legacy_mod.store_post = lambda request: legacy_plain  # CHANGED
            r = self.client.post(
                "/postpress-ai/store/",
                data=json.dumps({"title": "X", "content": "<p>Body</p>", "target": "draft"}),
                content_type="application/json",
                secure=True,
            )
        finally:
            legacy_mod.store_post = orig_store  # CHANGED

        self.assertEqual(r.status_code, 200)  # wrapper returns 200 with normalized failure payload
        data = json.loads(r.content.decode() or "{}")
        self.assertTrue(data.get("ok"))
        self.assertFalse(data.get("stored"))
        self.assertEqual(data.get("mode"), "failed")
        self.assertEqual(data.get("target_used"), "draft")
        self.assertEqual(data.get("wp_status"), "non-json")
        self.assertIn("wp_body", data)


@override_settings(
    ALLOWED_HOSTS=["testserver", "apps.techwithwayne.com"],
    PPA_SHARED_KEY="UNIT TEST KEY",
)
class AuthLoggingTests(TestCase):
    """Proves the raw key never appears in logs; only lengths/match flag are logged."""

    def setUp(self):
        self.client = Client(
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
            HTTP_X_PPA_KEY="UNIT TEST KEY",  # correct key
        )

    def test_no_secret_leak_in_logs(self):
        """
        Capture the 'webdoctor' logger and ensure it doesn't contain the raw key.
        It should log expected_len/provided_len/match flags, but never the key text.
        """
        raw_secret = "UNIT TEST KEY"

        with self.assertLogs("webdoctor", level="INFO") as lc:
            # Hit preview (fast, and triggers auth logging)
            r = self.client.post(
                "/postpress-ai/preview/",
                data=json.dumps({"subject": "LogCheck", "genre": "How-to", "tone": "Friendly"}),
                content_type="application/json",
                secure=True,
            )
            # Note: We only care about logs here; response can be anything JSON-ish.
            # If underlying preview callable returns non-JSON or errors, wrapper still emits logs.

        # Join captured logs into a single string to assert globally
        all_logs = "\n".join(lc.output)
        self.assertNotIn(raw_secret, all_logs, "Raw secret must not appear in logs")
        # Sanity: the auth log line is present and mentions expected/provided lengths.
        self.assertIn("[PPA][preview][auth]", all_logs)
        self.assertIn("expected_len=", all_logs)
        self.assertIn("provided_len=", all_logs)
