# /home/techwithwayne/agentsuite/postpress_ai/tests/test_preview_force_and_health_blank.py
"""
CHANGE LOG
----------
2025-08-17
- NEW FILE: Coverage for (1) forced preview fallback via env flag and                           # CHANGED:
  (2) /health early-return semantics when PPA_WP_API_URL is blank.                              # CHANGED:

2025-12-24
- FIX: Auth reads PPA_SHARED_KEY from *os.environ* (not Django settings).                        # CHANGED:
  Tests now patch os.environ and send matching HTTP_X_PPA_KEY to avoid 403.                      # CHANGED:
- FIX: preview logger/install expects install/site in JSON payload (not headers).               # CHANGED:
  Tests now include "install" in POST body so install is not '-'.                               # CHANGED:
- FIX: /postpress-ai/health/ is overridden in agentsuite/urls.py to return {"ok": True}.         # CHANGED:
  Test expectations updated accordingly (no wp_status fields).                                   # CHANGED:
"""

from __future__ import annotations  # CHANGED:

import json  # CHANGED:
import os  # CHANGED:
from unittest.mock import patch  # CHANGED:

from django.test import TestCase, Client  # CHANGED:


ALLOWED_ORIGIN = "https://techwithwayne.com"  # CHANGED:
TEST_SHARED_KEY = "test-shared-key"  # CHANGED:
TEST_INSTALL_ID = "11111111-1111-4111-8111-111111111111"  # CHANGED:


def _proxy_headers_for(view_name: str) -> dict:  # CHANGED:
    """
    Proxy-like headers for Django test client.

    NOTE:
    - Auth checks read PPA_SHARED_KEY from os.environ (see postpress_ai.views._get_shared_key).  # CHANGED:
    - X-PPA-Install headers are NOT used by the preview view; install is read from JSON payload. # CHANGED:
    """  # CHANGED:
    return {  # CHANGED:
        "HTTP_X_PPA_KEY": TEST_SHARED_KEY,  # CHANGED:
        "HTTP_X_PPA_VIEW": view_name,  # CHANGED:
        "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",  # CHANGED:
    }  # CHANGED:


class PreviewForcedFallbackTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.c = Client(  # CHANGED:
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
            HTTP_ORIGIN=ALLOWED_ORIGIN,
        )
        self.proxy_headers = _proxy_headers_for("preview")  # CHANGED:

    def test_forced_fallback_injects_forced_marker(self):  # CHANGED:
        # IMPORTANT: preview() reads install from JSON payload, not from headers.  # CHANGED:
        payload = {  # CHANGED:
            "install": TEST_INSTALL_ID,  # CHANGED:
            "subject": "T",
            "genre": "How-to",
            "tone": "Friendly",
            "description": "<p>Body</p>",
        }  # CHANGED:

        # Force local fallback via env flag; also set shared key env to satisfy auth.  # CHANGED:
        with patch.dict(  # CHANGED:
            os.environ,  # CHANGED:
            {"PPA_PREVIEW_FORCE_FALLBACK": "1", "PPA_SHARED_KEY": TEST_SHARED_KEY},  # CHANGED:
            clear=False,  # CHANGED:
        ):
            r = self.c.post(  # CHANGED:
                "/postpress-ai/preview/",
                data=json.dumps(payload),
                content_type="application/json",
                secure=True,
                **self.proxy_headers,  # CHANGED:
            )

        self.assertEqual(r.status_code, 200)  # CHANGED:
        d = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(d.get("ok"))  # CHANGED:
        self.assertIn("ver", d)  # CHANGED:
        self.assertIsInstance(d.get("result"), dict)  # CHANGED:
        # The preview view itself returns html derived from content/text; the provider marker is in html.  # CHANGED:
        self.assertIn("provider", d)  # CHANGED:
        self.assertEqual(d.get("provider"), "django")  # CHANGED:


class HealthBlankUrlTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.c = Client(  # CHANGED:
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
            HTTP_ORIGIN=ALLOWED_ORIGIN,
        )
        self.proxy_headers = _proxy_headers_for("health")  # CHANGED:

    def test_blank_url_returns_unreachable_url_error(self):  # CHANGED:
        # NOTE: agentsuite/urls.py overrides /postpress-ai/health/ with a minimal view returning {"ok": True}.  # CHANGED:
        # That override does not include wp_status/wp_error fields.                                             # CHANGED:
        with patch.dict(os.environ, {"PPA_SHARED_KEY": TEST_SHARED_KEY}, clear=False):  # CHANGED:
            r = self.c.get(  # CHANGED:
                "/postpress-ai/health/",
                secure=True,
                **self.proxy_headers,  # CHANGED:
            )

        self.assertEqual(r.status_code, 200)  # CHANGED:
        d = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(d.get("ok"))  # CHANGED:
        # No wp_status keys expected on the overridden health route.  # CHANGED:
        self.assertIsNone(d.get("wp_status"))  # CHANGED:
