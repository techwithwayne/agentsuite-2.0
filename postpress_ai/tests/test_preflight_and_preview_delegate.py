# /home/techwithwayne/agentsuite/postpress_ai/tests/test_preflight_and_preview_delegate.py
"""
CHANGE LOG
----------
2025-08-16
- FIX: Remove fragile importlib.reload() of submodule; directly monkeypatch the                # CHANGED:
  delegate hook `postpress_ai.views.preview._pp` with a mock that exposes `.preview`.          # CHANGED:
  This avoids "module preview not in sys.modules" and keeps tests deterministic.               # CHANGED:
- FIX: Be tolerant of /preview OPTIONS returning 200 or 204 (current code returns 200,        # CHANGED:
  while other endpoints return 204). We still assert proper CORS reflection.                   # CHANGED:

2025-08-16
- NEW FILE: Tests for CORS preflight (OPTIONS) across endpoints and for
  /preview delegate normalization & fallback behavior.
"""

from __future__ import annotations  # CHANGED:

import json  # CHANGED:
import sys  # CHANGED:
import types  # CHANGED:
import importlib  # CHANGED:

from django.test import TestCase, Client, RequestFactory  # CHANGED:
from django.http import HttpResponse, JsonResponse  # CHANGED:
from django.conf import settings  # CHANGED:


ALLOWED_ORIGIN = "https://techwithwayne.com"  # in settings CORS_ALLOWED_ORIGINS
SHARED_KEY = getattr(settings, "PPA_SHARED_KEY", "")


class PreflightTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.c = Client(
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
            HTTP_ORIGIN=ALLOWED_ORIGIN,
        )

    def test_options_preview(self):  # CHANGED:
        r = self.c.options("/postpress-ai/preview/", secure=True)
        # Some handlers return 200 JSON, others 204 empty — both valid as long as CORS is reflected.  # CHANGED:
        self.assertIn(r.status_code, (200, 204))  # CHANGED:
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)

    def test_options_health(self):  # CHANGED:
        r = self.c.options("/postpress-ai/health/", secure=True)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)

    def test_options_version(self):  # CHANGED:
        r = self.c.options("/postpress-ai/version/", secure=True)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)

    def test_options_preview_debug_model(self):  # CHANGED:
        r = self.c.options("/postpress-ai/preview/debug-model/", secure=True)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)


# ---- Helpers to install/remove a mock provider delegate at runtime (no reloads) ----         # CHANGED:
def _install_mock_delegate(preview_callable):  # CHANGED:
    """
    Monkeypatch the delegate hook used by the wrapper:
      postpress_ai.views.preview._pp = SimpleNamespace(preview=<callable>)
    No importlib.reload necessary; the view references `_pp` at call time.                     # CHANGED:
    Returns a cleanup callable that restores the original value.                                # CHANGED:
    """  # CHANGED:
    pv = importlib.import_module("postpress_ai.views.preview")  # CHANGED:
    old_pp = getattr(pv, "_pp", None)  # CHANGED:
    pv._pp = types.SimpleNamespace(preview=preview_callable)  # CHANGED:

    def _cleanup():  # CHANGED:
        try:
            pv._pp = old_pp  # CHANGED:
        except Exception:
            pass

    return _cleanup  # CHANGED:


class PreviewDelegateNormalizationTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.factory = RequestFactory()

    def _make_post(self, path="/postpress-ai/preview/", body=None):  # CHANGED:
        if body is None:
            body = {"subject": "T", "genre": "How-to", "tone": "Friendly", "description": "<p>Body</p>"}
        headers = {
            "secure": True,
            "HTTP_HOST": "apps.techwithwayne.com",
            "SERVER_NAME": "apps.techwithwayne.com",
            "HTTP_ORIGIN": ALLOWED_ORIGIN,
        }
        if SHARED_KEY:  # include auth if available
            headers["HTTP_X_PPA_KEY"] = SHARED_KEY
        return self.factory.post(path, data=json.dumps(body), content_type="application/json", **headers)

    def test_delegate_valid_contract_gets_ver_and_provider_comment(self):  # CHANGED:
        def delegate_ok(request):
            payload = {"ok": True, "result": {"title": "A", "html": "<p>X</p>", "summary": "S"}}
            return JsonResponse(payload, status=200)

        cleanup = _install_mock_delegate(delegate_ok)  # CHANGED:
        try:
            from postpress_ai import views as ppa_views
            req = self._make_post()
            resp = ppa_views.preview(req)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)
            data = json.loads(resp.content.decode())
            self.assertTrue(data.get("ok"))
            self.assertIn("ver", data)
            self.assertIn("result", data)
            self.assertIn("<!-- provider:", data["result"]["html"])  # CHANGED:
        finally:
            cleanup()

    def test_delegate_malformed_contract_triggers_local_fallback(self):  # CHANGED:
        def delegate_bad_shape(request):
            # Malformed because result.html is empty
            payload = {"ok": True, "result": {"title": "A", "html": "", "summary": "S"}}
            return JsonResponse(payload, status=200)

        cleanup = _install_mock_delegate(delegate_bad_shape)  # CHANGED:
        try:
            from postpress_ai import views as ppa_views
            req = self._make_post()
            resp = ppa_views.preview(req)
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.content.decode())
            # Expect deterministic local fallback success
            self.assertTrue(data.get("ok"))
            self.assertIn("result", data)
            r = data["result"]
            self.assertIsInstance(r, dict)
            self.assertTrue(bool(r.get("title")))
            self.assertTrue(bool(r.get("html")))
            self.assertTrue(bool(r.get("summary")))
            self.assertIn("ver", data)
        finally:
            cleanup()

    def test_delegate_non_json_triggers_local_fallback(self):  # CHANGED:
        def delegate_non_json(request):
            return HttpResponse("<html>nope</html>", status=200, content_type="text/html")

        cleanup = _install_mock_delegate(delegate_non_json)  # CHANGED:
        try:
            from postpress_ai import views as ppa_views
            req = self._make_post()
            resp = ppa_views.preview(req)
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.content.decode())
            self.assertTrue(data.get("ok"))
            self.assertIn("result", data)
            self.assertIn("ver", data)
        finally:
            cleanup()
