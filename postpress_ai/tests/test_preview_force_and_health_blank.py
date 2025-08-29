# /home/techwithwayne/agentsuite/postpress_ai/tests/test_preview_force_and_health_blank.py
"""
CHANGE LOG
----------
2025-08-17
- NEW FILE: Coverage for (1) forced preview fallback via env flag and                           # CHANGED:
  (2) /health early-return semantics when PPA_WP_API_URL is blank.                              # CHANGED:
"""

from __future__ import annotations  # CHANGED:

import json  # CHANGED:
import os  # CHANGED:
from unittest.mock import patch  # CHANGED:

from django.test import TestCase, Client  # CHANGED:
from django.test.utils import override_settings  # CHANGED:


ALLOWED_ORIGIN = "https://techwithwayne.com"  # CHANGED:


class PreviewForcedFallbackTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.c = Client(HTTP_HOST="apps.techwithwayne.com", SERVER_NAME="apps.techwithwayne.com",
                        HTTP_ORIGIN=ALLOWED_ORIGIN)  # CHANGED:

    def test_forced_fallback_injects_forced_marker(self):  # CHANGED:
        payload = {"subject":"T","genre":"How-to","tone":"Friendly","description":"<p>Body</p>"}  # CHANGED:
        # Force fallback via env flag and ensure we get a valid success shape + provider marker. # CHANGED:
        with patch.dict(os.environ, {"PPA_PREVIEW_FORCE_FALLBACK": "1"}, clear=False):  # CHANGED:
            r = self.c.post("/postpress-ai/preview/", data=json.dumps(payload),
                            content_type="application/json", secure=True)  # CHANGED:
        self.assertEqual(r.status_code, 200)  # CHANGED:
        d = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(d.get("ok"))  # CHANGED:
        self.assertIn("ver", d)  # CHANGED:
        self.assertIsInstance(d.get("result"), dict)  # CHANGED:
        self.assertIn("<!-- provider: forced -->", d["result"]["html"])  # CHANGED:


class HealthBlankUrlTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.c = Client(HTTP_HOST="apps.techwithwayne.com", SERVER_NAME="apps.techwithwayne.com",
                        HTTP_ORIGIN=ALLOWED_ORIGIN)  # CHANGED:

    def test_blank_url_returns_unreachable_url_error(self):  # CHANGED:
        with override_settings(PPA_WP_API_URL=""):  # CHANGED:
            r = self.c.get("/postpress-ai/health/", secure=True)  # CHANGED:
        self.assertEqual(r.status_code, 200)  # CHANGED:
        d = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(d.get("ok"))  # CHANGED:
        self.assertEqual(d.get("wp_status"), "unreachable")  # CHANGED:
        self.assertEqual(d.get("wp_error"), "url-error")  # CHANGED:
        self.assertFalse(d.get("wp_reachable"))  # CHANGED:
        self.assertFalse(d.get("wp_allowed"))  # CHANGED:
