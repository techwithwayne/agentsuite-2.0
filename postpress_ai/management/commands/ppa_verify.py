# -*- coding: utf-8 -*-
"""
CHANGE LOG
- 2025-08-15: Initial creation of management command `ppa_verify`.
  Provides a single-shot local verifier that reproduces Wayne's manual checks.

- 2025-08-15: Fix HTTPS redirects for GET checks.  # CHANGED:
  * Health, Version, and Preview-Debug now use secure=True so Django's test
    client simulates HTTPS requests and avoids 301 redirects when
    SECURE_SSL_REDIRECT=True in settings.
"""

from __future__ import annotations

import json
import os
from django.core.management.base import BaseCommand, CommandParser
from django.test import Client
from django.urls import resolve, Resolver404


class Command(BaseCommand):
    help = "Runs PostPress AI local verifications (router, preview, store, health, version) safely."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--host",
            default="apps.techwithwayne.com",
            help="HTTP Host header to simulate CF proxied hostname (default: apps.techwithwayne.com).",
        )
        parser.add_argument(
            "--path",
            default="/postpress-ai",
            help="URL base path where PostPress AI is mounted (default: /postpress-ai).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print full JSON payloads.",
        )

    def handle(self, *args, **opts) -> None:
        base_path: str = str(opts.get("path") or "/postpress-ai").rstrip("/")
        host: str = str(opts.get("host") or "apps.techwithwayne.com")
        verbose: bool = bool(opts.get("verbose") or False)

        # NOTE: We create two clients:
        #   - client: for endpoints that do NOT require X-PPA-Key
        #   - auth_client: for endpoints that DO require X-PPA-Key
        # We never print the secret; we only print its presence and length.
        client = Client(HTTP_HOST=host, SERVER_NAME=host)
        key_raw = os.getenv("PPA_SHARED_KEY") or ""
        key_len = len(key_raw)
        has_key = bool(key_len)
        auth_client = Client(HTTP_HOST=host, SERVER_NAME=host, HTTP_X_PPA_KEY=key_raw)

        self.stdout.write(self.style.NOTICE(f"[verify] host={host} base_path={base_path}"))
        self.stdout.write(self.style.NOTICE(f"[verify] key_present={has_key} key_len={key_len}  # secret not printed"))

        # 1) Router → module resolution
        try:
            mod = resolve(f"{base_path}/preview/").func.__module__
            ok = (mod == "postpress_ai.views")
            self._report("router", ok, detail=f"resolved={mod!r}")
            if not ok:
                self._maybe_exit(1)
        except Resolver404 as ex:
            self._report("router", False, detail=f"Resolver404: {ex}")
            return

        # 2) /preview/ (auth, HTTPS)
        payload = {
            "subject": "Router Test",
            "genre": "How-to",
            "tone": "Friendly",
            "description": "<p>Body</p>",
        }
        r = auth_client.post(
            f"{base_path}/preview/",
            data=json.dumps(payload),
            content_type="application/json",
            secure=True,  # simulate HTTPS
        )
        ok = (r.status_code == 200)
        prev_text = r.content.decode("utf-8", errors="replace")
        prev_ct = r.headers.get("Content-Type")
        self._report("preview", ok, detail=f"status={r.status_code} ct={prev_ct}")
        if verbose:
            self._dump_json("preview.json", prev_text)

        # 3) /store/ (auth, HTTPS; contract says ALWAYS HTTP 200)
        store_payload = {
            "title": "PPA Normalization Test",
            "content": "<p>Body</p>",
            "target": "draft",
        }
        r = auth_client.post(
            f"{base_path}/store/",
            data=json.dumps(store_payload),
            content_type="application/json",
            secure=True,  # simulate HTTPS
        )
        ok = (r.status_code == 200)
        st_text = r.content.decode("utf-8", errors="replace")
        st_ct = r.headers.get("Content-Type")
        self._report("store", ok, detail=f"status={r.status_code} ct={st_ct}")
        if verbose:
            self._dump_json("store.json", st_text)

        # 4) /health/ (NO auth) — use HTTPS to avoid SECURE_SSL_REDIRECT 301
        r = client.get(f"{base_path}/health/", secure=True)  # CHANGED: add secure=True to avoid 301
        ok = (r.status_code == 200)
        h_text = r.content.decode("utf-8", errors="replace")
        h_ct = r.headers.get("Content-Type")
        self._report("health", ok, detail=f"status={r.status_code} ct={h_ct}")
        if verbose:
            self._dump_json("health.json", h_text)

        # 5) /version/ (NO auth) — use HTTPS to avoid SECURE_SSL_REDIRECT 301
        r = client.get(f"{base_path}/version/", secure=True)  # CHANGED: add secure=True to avoid 301
        ok = (r.status_code == 200)
        v_text = r.content.decode("utf-8", errors="replace")
        v_ct = r.headers.get("Content-Type")
        self._report("version", ok, detail=f"status={r.status_code} ct={v_ct}")
        if verbose:
            self._dump_json("version.json", v_text)

        # 6) /preview/debug-model/ (auth) — use HTTPS to avoid SECURE_SSL_REDIRECT 301
        r = auth_client.get(f"{base_path}/preview/debug-model/", secure=True)  # CHANGED: add secure=True to avoid 301
        ok = (r.status_code == 200)
        pd_text = r.content.decode("utf-8", errors="replace")
        pd_ct = r.headers.get("Content-Type")
        self._report("preview-debug", ok, detail=f"status={r.status_code} ct={pd_ct}")
        if verbose:
            self._dump_json("preview-debug.json", pd_text)

        self.stdout.write(self.style.SUCCESS("[verify] Complete."))

    # ----- helpers -----
    def _report(self, name: str, ok: bool, *, detail: str = "") -> None:
        flag = "PASS" if ok else "FAIL"
        msg = f"[{name}] {flag}"
        if detail:
            msg += f" — {detail}"
        if ok:
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stdout.write(self.style.ERROR(msg))

    def _dump_json(self, fname: str, text: str) -> None:
        """Pretty prints JSON if possible; otherwise writes raw text."""
        try:
            data = json.loads(text)
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            pretty = text
        self.stdout.write(self.style.NOTICE(f"[dump] {fname}"))
        self.stdout.write(pretty)

    def _maybe_exit(self, code: int) -> None:
        """Exit early if a hard precondition fails (e.g., routing)."""
        raise SystemExit(code)
