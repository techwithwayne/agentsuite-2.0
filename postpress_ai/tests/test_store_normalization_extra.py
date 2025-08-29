# /home/techwithwayne/agentsuite/postpress_ai/tests/test_store_normalization_extra.py
"""
CHANGE LOG
----------
2025-08-16
- NEW FILE: Extra tests for /store normalization wrappers, including:                           # CHANGED:
  • dict status coercion from string → int                                                     # CHANGED:
  • failure body propagation from wp_body/body/message/error                                    # CHANGED:
  • HttpResponse success with URL target → target_used fallback                                 # CHANGED:
  • HttpResponse non-JSON failure normalization                                                 # CHANGED:
"""

from __future__ import annotations  # CHANGED:

import json  # CHANGED:
import importlib  # CHANGED:
from types import SimpleNamespace  # CHANGED:

from django.test import TestCase, Client  # CHANGED:
from django.http import HttpResponse, JsonResponse  # CHANGED:
from django.conf import settings  # CHANGED:


ALLOWED_ORIGIN = "https://techwithwayne.com"  # CHANGED:
SHARED_KEY = getattr(settings, "PPA_SHARED_KEY", "")  # CHANGED:


class StoreNormalizationExtraTests(TestCase):  # CHANGED:
    def setUp(self):  # CHANGED:
        self.client = Client(  # CHANGED:
            HTTP_HOST="apps.techwithwayne.com",
            SERVER_NAME="apps.techwithwayne.com",
            HTTP_ORIGIN=ALLOWED_ORIGIN,
            **({"HTTP_X_PPA_KEY": SHARED_KEY} if SHARED_KEY else {}),
        )
        # Prepare delegate hook monkeypatch handle                                              # CHANGED:
        self.views_pkg = importlib.import_module("postpress_ai.views")  # CHANGED:
        self._old_delegate = getattr(self.views_pkg, "STORE_DELEGATE", None)  # CHANGED:

    def tearDown(self):  # CHANGED:
        # Restore original delegate to avoid test cross-talk                                   # CHANGED:
        self.views_pkg.STORE_DELEGATE = self._old_delegate  # CHANGED:

    def _set_delegate(self, fn):  # CHANGED:
        """Install a temporary STORE_DELEGATE callable."""  # CHANGED:
        self.views_pkg.STORE_DELEGATE = fn  # CHANGED:

    def _post_store(self, payload: dict):  # CHANGED:
        return self.client.post(  # CHANGED:
            "/postpress-ai/store/",
            data=json.dumps(payload),
            content_type="application/json",
            secure=True,
        )  # CHANGED:

    def test_dict_status_string_coerced_success(self):  # CHANGED:
        """Legacy dict with status='201' → success, wp_status=201, stored:true."""  # CHANGED:
        def delegate_ok(request):  # CHANGED:
            return {  # CHANGED:
                "status": "201",  # string; wrapper must coerce to int                         # CHANGED:
                "id": 101,  # CHANGED:
                "target": "draft",  # CHANGED:
                "wp_status": 201,  # CHANGED:
            }  # CHANGED:

        self._set_delegate(delegate_ok)  # CHANGED:
        r = self._post_store({"title": "X", "html": "<p>Body</p>", "target": "draft"})  # CHANGED:
        self.assertEqual(r.status_code, 200)  # CHANGED:
        data = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(data.get("ok"))  # CHANGED:
        self.assertTrue(data.get("stored"))  # CHANGED:
        self.assertEqual(data.get("wp_status"), 201)  # CHANGED:
        self.assertEqual(data.get("mode"), "created")  # CHANGED:
        self.assertEqual(data.get("target_used"), "draft")  # CHANGED:
        self.assertIn("ver", data)  # CHANGED:

    def test_dict_failure_message_propagation(self):  # CHANGED:
        """Failure dict with 'message' should map to wp_body."""  # CHANGED:
        def delegate_fail(request):  # CHANGED:
            return {  # CHANGED:
                "status": 400,  # CHANGED:
                "id": None,  # CHANGED:
                "target": "draft",  # CHANGED:
                "message": "Nope: invalid payload",  # CHANGED:
            }  # CHANGED:

        self._set_delegate(delegate_fail)  # CHANGED:
        r = self._post_store({"title": "X", "html": "<p>Body</p>", "target": "draft"})  # CHANGED:
        self.assertEqual(r.status_code, 200)  # CHANGED:
        data = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(data.get("ok"))  # CHANGED:
        self.assertFalse(data.get("stored"))  # CHANGED:
        self.assertEqual(data.get("mode"), "failed")  # CHANGED:
        self.assertEqual(data.get("wp_status"), 400)  # CHANGED:
        self.assertEqual(data.get("wp_body"), "Nope: invalid payload")  # CHANGED:
        self.assertIn("ver", data)  # CHANGED:

    def test_httpresponse_success_url_target_fallback(self):  # CHANGED:
        """HttpResponse 201 with target URL → wrapper must use requested target."""  # CHANGED:
        def delegate_resp(request):  # CHANGED:
            payload = {"id": 202, "target": "https://techwithwayne.com/wp-json/wp/v2"}  # CHANGED:
            return JsonResponse(payload, status=201)  # CHANGED:

        self._set_delegate(delegate_resp)  # CHANGED:
        r = self._post_store({"title": "X", "html": "<p>Body</p>", "target": "draft"})  # CHANGED:
        self.assertEqual(r.status_code, 200)  # CHANGED:
        data = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(data.get("stored"))  # CHANGED:
        self.assertEqual(data.get("mode"), "created")  # CHANGED:
        self.assertEqual(data.get("target_used"), "draft")  # CHANGED:
        self.assertEqual(data.get("wp_status"), 201)  # CHANGED:
        self.assertIn("ver", data)  # CHANGED:

    def test_httpresponse_non_json_failure_normalized(self):  # CHANGED:
        """Non-JSON HttpResponse failure → normalized failure with wp_status='non-json'."""  # CHANGED:
        def delegate_nonjson_fail(request):  # CHANGED:
            return HttpResponse("oops not json", status=500, content_type="text/html")  # CHANGED:

        self._set_delegate(delegate_nonjson_fail)  # CHANGED:
        r = self._post_store({"title": "X", "html": "<p>Body</p>", "target": "draft"})  # CHANGED:
        self.assertEqual(r.status_code, 200)  # CHANGED:
        data = json.loads(r.content.decode())  # CHANGED:
        self.assertTrue(data.get("ok"))  # CHANGED:
        self.assertFalse(data.get("stored"))  # CHANGED:
        self.assertEqual(data.get("mode"), "failed")  # CHANGED:
        self.assertEqual(data.get("wp_status"), "non-json")  # CHANGED:
        self.assertIsInstance(data.get("wp_body"), str)  # CHANGED:
        self.assertIn("ver", data)  # CHANGED:
