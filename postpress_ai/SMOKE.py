# /home/techwithwayne/agentsuite/postpress_ai/SMOKE.py
"""
CHANGE LOG
----------
2025-08-17
- FIX: Avoid `{}` dict literal inside an f-string expression (Python forbids braces            # CHANGED:
  within f-string expressions). Compute the value first, or use `dict()` to avoid braces.      # CHANGED:
  This resolves `SyntaxError: f-string: expecting '}'` on the preview line.                    # CHANGED:

2025-08-17
- NEW FILE: Lightweight smoke check that hits all public endpoints via Django's
  test client (same process), validates response *shapes* per contract, and prints
  a concise PASS/FAIL summary. No external libs, no secrets printed.

Usage (preferred):
    ./venv/bin/python manage.py shell -c "import postpress_ai.SMOKE as s; s.main()"

Notes:
- Runs entirely in-process using Django's Client with HTTPS emulation (secure=True).
- Uses Host=apps.techwithwayne.com and reflects CORS for origin=https://techwithwayne.com.
- For /store/, success depends on a delegate being available. The smoke test only asserts
  normalized envelope compliance (HTTP 200 + shape) — not that storage succeeded.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

from django.test import Client


ALLOWED_ORIGIN = "https://techwithwayne.com"
HOST = "apps.techwithwayne.com"


def _print(msg: str) -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _ok(b: bool) -> str:
    return "PASS ✅" if b else "FAIL ❌"


def _json(resp) -> Dict[str, Any]:
    try:
        return json.loads(resp.content.decode("utf-8"))
    except Exception:
        return {}


def main() -> int:
    failures = 0

    key = os.getenv("PPA_SHARED_KEY") or ""
    key_len = len(key)

    # Build a client; pass Origin to exercise CORS reflection code paths.
    c = Client(HTTP_HOST=HOST, SERVER_NAME=HOST, HTTP_ORIGIN=ALLOWED_ORIGIN)

    _print("=== PostPress AI Smoke ===")
    _print(f"env: PPA_SHARED_KEY length = {key_len}")

    # 1) /version/
    r = c.get("/postpress-ai/version/", secure=True)
    d = _json(r)
    ok = (r.status_code == 200 and d.get("ok") is True and isinstance(d.get("ver"), str) and
          d.get("module") == "postpress_ai.views" and isinstance(d.get("file"), str))
    _print(f"[version] { _ok(ok) } status={r.status_code} ver={d.get('ver')}")
    failures += 0 if ok else 1

    # 2) /health/
    r = c.get("/postpress-ai/health/", secure=True)
    d = _json(r)
    ok = (r.status_code == 200 and d.get("ok") is True and "wp_status" in d and
          isinstance(d.get("wp_reachable"), bool) and isinstance(d.get("wp_allowed"), bool))
    _print(f"[health] { _ok(ok) } status={r.status_code} wp_status={d.get('wp_status')} reachable={d.get('wp_reachable')} allowed={d.get('wp_allowed')}")
    failures += 0 if ok else 1

    # 3) /preview/ (authorized; wrapper path or provider delegate)
    payload = {"subject": "Smoke Test", "genre": "How-to", "tone": "Friendly", "description": "<p>Body</p>"}
    r = c.post("/postpress-ai/preview/", data=json.dumps(payload), content_type="application/json",
               secure=True, **({"HTTP_X_PPA_KEY": key} if key else {}))
    d = _json(r)
    ok = (r.status_code == 200 and d.get("ok") is True and isinstance(d.get("result"), dict) and
          all(isinstance(d["result"].get(k), str) and d["result"][k] for k in ("title", "html", "summary")))
    title_val = (d.get("result") or dict()).get("title")  # CHANGED: precompute to avoid `{}` in f-string
    _print(f"[preview] { _ok(ok) } status={r.status_code} title={title_val!r}")  # CHANGED:

    failures += 0 if ok else 1

    # 4) /store/ (normalized envelope; may be success or normalized failure depending on delegate availability)
    r = c.post("/postpress-ai/store/", data=json.dumps({"title": "Smoke", "content": "<p>Body</p>", "target": "draft"}),
               content_type="application/json", secure=True, **({"HTTP_X_PPA_KEY": key} if key else {}))
    d = _json(r)
    ok = (r.status_code == 200 and d.get("ok") is True and d.get("mode") in ("created", "failed") and
          d.get("target_used") is not None and "wp_status" in d and "stored" in d)
    _print(f"[store]   { _ok(ok) } status={r.status_code} stored={d.get('stored')} mode={d.get('mode')} wp_status={d.get('wp_status')}")
    failures += 0 if ok else 1

    # 5) /preview/debug-model/ (auth required; tolerate 403 when key missing)
    r = c.get("/postpress-ai/preview/debug-model/", secure=True, **({"HTTP_X_PPA_KEY": key} if key else {}))
    if r.status_code == 200:
        d = _json(r)
        ok = (d.get("ok") is True and "provider" in d and "model" in d and "ver" in d)
        _print(f"[debug]  { _ok(ok) } status=200 provider={d.get('provider')} model={d.get('model')}")
        failures += 0 if ok else 1
    else:
        ok = (r.status_code == 403)
        _print(f"[debug]  { _ok(ok) } status={r.status_code} (expected 200 with key or 403 without)")
        failures += 0 if ok else 1

    _print(f"=== Result: { 'ALL PASS ✅' if failures == 0 else f'{failures} CHECK(S) FAILED ❌' } ===")
    return failures


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
