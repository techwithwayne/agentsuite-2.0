# /home/techwithwayne/agentsuite/postpress_ai/tests/test_cors_reflection.py
"""
CHANGE LOG
----------
2025-08-17
- NEW FILE: CORS reflection tests to ensure:                                                     # CHANGED:
  • Allowed origin is reflected with correct headers                                             # CHANGED:
  • Unknown origin is NOT reflected (no A-C-A-Origin header)                                     # CHANGED:
  • Behavior holds across GET/POST/OPTIONS and multiple endpoints                                # CHANGED:
"""

from __future__ import annotations  # CHANGED:

from django.test import TestCase, Client  # CHANGED:

# We use the known good origin as configured in settings/infra.                                 # CHANGED:
ALLOWED_ORIGIN = "https://techwithwayne.com"  # CHANGED:
UNKNOWN_ORIGIN = "https://unknown.example"    # CHANGED:


class CorsReflectionTests(TestCase):  # CHANGED:
    """Validate that CORS is reflected only for explicitly allowed origins."""  # CHANGED:

    def setUp(self):  # CHANGED:
        # Clients with different Origin headers                                                 # CHANGED:
        self.c_allowed = Client(                                                               # CHANGED:
            HTTP_HOST="apps.techwithwayne.com",                                                # CHANGED:
            SERVER_NAME="apps.techwithwayne.com",                                              # CHANGED:
            HTTP_ORIGIN=ALLOWED_ORIGIN,                                                        # CHANGED:
        )                                                                                      # CHANGED:
        self.c_unknown = Client(                                                               # CHANGED:
            HTTP_HOST="apps.techwithwayne.com",                                                # CHANGED:
            SERVER_NAME="apps.techwithwayne.com",                                              # CHANGED:
            HTTP_ORIGIN=UNKNOWN_ORIGIN,                                                        # CHANGED:
        )                                                                                      # CHANGED:

    # ---------- OPTIONS (preflight) paths ----------                                           # CHANGED:
    def test_preview_options_reflects_allowed(self):  # CHANGED:
        r = self.c_allowed.options("/postpress-ai/preview/", secure=True)                      # CHANGED:
        self.assertEqual(r.status_code, 204)                                                   # CHANGED:
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)         # CHANGED:

    def test_preview_options_not_reflect_unknown(self):  # CHANGED:
        r = self.c_unknown.options("/postpress-ai/preview/", secure=True)                      # CHANGED:
        self.assertEqual(r.status_code, 204)                                                   # CHANGED:
        self.assertIsNone(r.headers.get("Access-Control-Allow-Origin"))                        # CHANGED:

    def test_health_options_reflects_allowed(self):  # CHANGED:
        r = self.c_allowed.options("/postpress-ai/health/", secure=True)                       # CHANGED:
        self.assertEqual(r.status_code, 204)                                                   # CHANGED:
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)         # CHANGED:

    def test_health_options_not_reflect_unknown(self):  # CHANGED:
        r = self.c_unknown.options("/postpress-ai/health/", secure=True)                       # CHANGED:
        self.assertEqual(r.status_code, 204)                                                   # CHANGED:
        self.assertIsNone(r.headers.get("Access-Control-Allow-Origin"))                        # CHANGED:

    # ---------- GET paths ----------                                                            # CHANGED:
    def test_health_get_reflects_allowed(self):  # CHANGED:
        r = self.c_allowed.get("/postpress-ai/health/", secure=True)                           # CHANGED:
        self.assertEqual(r.status_code, 200)                                                   # CHANGED:
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)         # CHANGED:

    def test_version_get_not_reflect_unknown(self):  # CHANGED:
        r = self.c_unknown.get("/postpress-ai/version/", secure=True)                          # CHANGED:
        self.assertEqual(r.status_code, 200)                                                   # CHANGED:
        self.assertIsNone(r.headers.get("Access-Control-Allow-Origin"))                        # CHANGED:

    # ---------- POST paths ----------                                                           # CHANGED:
    def test_store_post_reflects_allowed(self):  # CHANGED:
        # Test client bypasses auth in our code, so no key required.                            # CHANGED:
        import json                                                                             # CHANGED:
        r = self.c_allowed.post(                                                                # CHANGED:
            "/postpress-ai/store/",                                                             # CHANGED:
            data=json.dumps({"title": "CORS", "content": "<p>Body</p>", "target": "draft"}),   # CHANGED:
            content_type="application/json",                                                    # CHANGED:
            secure=True,                                                                        # CHANGED:
        )                                                                                       # CHANGED:
        self.assertEqual(r.status_code, 200)                                                   # CHANGED:
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)         # CHANGED:

    def test_store_post_not_reflect_unknown(self):  # CHANGED:
        import json                                                                             # CHANGED:
        r = self.c_unknown.post(                                                                # CHANGED:
            "/postpress-ai/store/",                                                             # CHANGED:
            data=json.dumps({"title": "CORS", "content": "<p>Body</p>", "target": "draft"}),   # CHANGED:
            content_type="application/json",                                                    # CHANGED:
            secure=True,                                                                        # CHANGED:
        )                                                                                       # CHANGED:
        self.assertEqual(r.status_code, 200)                                                   # CHANGED:
        self.assertIsNone(r.headers.get("Access-Control-Allow-Origin"))                        # CHANGED:
