#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostPress AI — Simple API Client (Preview + Store)

CHANGE LOG
----------
2025-08-14  (v1) Initial client.
2025-08-14  (v2) CHANGED:
- Add browser-like headers (User-Agent, Accept, Accept-Language) so Cloudflare is
  less likely to serve a Managed Challenge to this non-browser client.
- Detect Cloudflare "Just a moment..." HTML and print a clear DIAG with next steps:
  * Suggest a Cloudflare WAF rule to Bypass/Skip Challenge for path `/postpress-ai/*`.
  * Suggest testing via PythonAnywhere default domain (bypasses Cloudflare) as a temporary dev base.
- Improve error printing (show status + top 300 chars of raw HTML if non-JSON).
- Add `--ua` to override User-Agent if needed.

USAGE
-----
# Preview
~/agentsuite/venv/bin/python ~/agentsuite/tools/ppa_client.py preview \
  --base https://apps.techwithwayne.com/postpress-ai \
  --key "YOUR_SHARED_KEY" \
  --subject "Router Test" --genre "How-to" --tone "Friendly"

# Store
~/agentsuite/venv/bin/python ~/agentsuite/tools/ppa_client.py store \
  --base https://apps.techwithwayne.com/postpress-ai \
  --key "YOUR_SHARED_KEY" \
  --title "PPA Normalization Test" --content "<p>Body</p>" --target draft

# Cloudflare still blocking?
# 1) TEMP: use your PythonAnywhere default domain to bypass CF entirely:
#    --base https://<your-username>.pythonanywhere.com/postpress-ai
# 2) PERM: add a Cloudflare rule to Skip Managed Challenge for path /postpress-ai/*
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple

CLOUDFLARE_MARKERS = (
    "Just a moment...",
    "challenge-platform",
    "__cf_chl_",
    "cf-nel",
    "window._cf_chl_opt",
)


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(obj)


def _build_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}"


def _looks_like_cloudflare_html(raw: str) -> bool:
    low = raw.lower()
    return any(marker.lower() in low for marker in CLOUDFLARE_MARKERS)


def _cf_help(url: str) -> None:
    print("\n[DIAG] Cloudflare Managed Challenge detected before Django handled the request.")
    print("      To unblock API calls from non-browser clients (like this script):")
    print("      1) In Cloudflare → Security → WAF → Custom rules, add:")
    print("         - IF: http.request.uri.path contains \"/postpress-ai/\"")
    print("         - THEN: Skip Managed Challenge / Bypass Super Bot Fight Mode")
    print("      2) Alternatively create a dedicated subdomain (e.g., api.apps.techwithwayne.com)")
    print("         with Security Level = Essentially Off or a Path-based Skip Rule for /postpress-ai/*")
    print("      3) For immediate dev testing, use your PythonAnywhere default domain as base, e.g.:")
    print("         --base https://<your-username>.pythonanywhere.com/postpress-ai")
    print(f"      URL that was blocked: {url}")


def _post_json(url: str, key: str, payload: Dict[str, Any], ua: str) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
    """
    POST JSON using urllib (stdlib only). Returns (status_code, json_body_or_diag, headers_dict).

    - We send browser-ish headers to reduce Cloudflare bot challenges.
    - If non-JSON body is returned, we synthesize a helpful error payload.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            # Browser-like headers (helps with some CF configurations)
            "User-Agent": ua,
            "Accept": "application/json,text/html;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "X-PPA-Key": key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.getcode() or 0
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except Exception:
                # Non-JSON (likely Cloudflare challenge HTML). Truncate for readability.
                snippet = (raw[:300] + "…") if len(raw) > 300 else raw
                body = {"ok": False, "error": "non_json_response", "status": status, "raw_snippet": snippet}
            headers = {k.lower(): v for k, v in resp.headers.items()}
            # If it smells like Cloudflare HTML, print guidance.
            if isinstance(body, dict) and body.get("error") == "non_json_response" and _looks_like_cloudflare_html(raw):
                _cf_help(url)
            return status, body, headers
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            snippet = (raw[:300] + "…") if len(raw) > 300 else raw
            body = {"ok": False, "error": "http_error", "status": status, "raw_snippet": snippet}
            if _looks_like_cloudflare_html(raw):
                _cf_help(url)
        headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return status, body, headers
    except urllib.error.URLError as e:
        return 0, {"ok": False, "error": "network_error", "detail": str(e)}, {}
    except Exception as e:
        return 0, {"ok": False, "error": "unexpected_client_error", "detail": str(e)}, {}


def _require_ver(body: Dict[str, Any]) -> None:
    """
    Validate that the response includes a top-level 'ver' field. Print a warning if missing.
    (If Cloudflare blocked us, there won't be a 'ver'.)
    """
    if isinstance(body, dict) and "ver" in body:
        return
    print("WARNING: Response missing 'ver' field (likely blocked upstream or non-JSON).", file=sys.stderr)


def run_preview(args: argparse.Namespace) -> int:
    url = _build_url(args.base, "preview/")
    payload = {"subject": args.subject, "genre": args.genre, "tone": args.tone}
    _print_header(f"[PPA] PREVIEW → {url}")
    print(f"[key] len={len(args.key)} • starts_with='{args.key[:3]}' • ends_with='{args.key[-3:]}' (value hidden)")

    status, body, headers = _post_json(url, args.key, payload, ua=args.ua)

    _print_header(f"[PPA] PREVIEW ← status={status}")
    print(_pretty(body))
    _require_ver(body)

    # Non-fatal for 4xx/5xx; we want diagnostics. Exit 0 unless network totally failed.
    return 0 if status else 1


def run_store(args: argparse.Namespace) -> int:
    url = _build_url(args.base, "store/")
    payload = {"title": args.title, "content": args.content, "target": args.target}
    _print_header(f"[PPA] STORE → {url}")
    print(f"[key] len={len(args.key)} • starts_with='{args.key[:3]}' • ends_with='{args.key[-3:]}' (value hidden)")

    status, body, headers = _post_json(url, args.key, payload, ua=args.ua)

    _print_header(f"[PPA] STORE ← status={status}")
    print(_pretty(body))
    _require_ver(body)

    return 0 if status else 1


def run_chain(args: argparse.Namespace) -> int:
    pcode = run_preview(args)
    print("\n---\nPreview complete. Proceeding to Store...\n---\n")
    scode = run_store(args)
    return 0 if (pcode == 0 and scode == 0) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PostPress AI API client (preview + store).",
        epilog="Tip: If Cloudflare blocks, use --base https://<username>.pythonanywhere.com/postpress-ai or add a CF WAF bypass for /postpress-ai/*.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base", required=True, help="Base URL, e.g. https://apps.techwithwayne.com/postpress-ai")
    common.add_argument("--key", default=os.getenv("PPA_SHARED_KEY", ""), help="Shared X-PPA-Key or set PPA_SHARED_KEY env var")
    common.add_argument(
        "--ua",
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        help="User-Agent string to send (default is a common desktop browser UA).",
    )

    # preview
    p = sub.add_parser("preview", parents=[common], help="Call /preview/ endpoint")
    p.add_argument("--subject", required=True)
    p.add_argument("--genre", required=True)
    p.add_argument("--tone", required=True)
    p.set_defaults(func=run_preview)

    # store
    s = sub.add_parser("store", parents=[common], help="Call /store/ endpoint")
    s.add_argument("--title", required=True)
    s.add_argument("--content", required=True)
    s.add_argument("--target", default="draft", choices=["draft", "publish", "pending"])
    s.set_defaults(func=run_store)

    # chain
    c = sub.add_parser("chain", parents=[common], help="preview -> store")
    c.add_argument("--subject", required=True)
    c.add_argument("--genre", required=True)
    c.add_argument("--tone", required=True)
    c.add_argument("--title", default="PPA Draft from Chain")
    c.add_argument("--content", default="<p>Draft body from ppa_client chain test.</p>")
    c.add_argument("--target", default="draft", choices=["draft", "publish", "pending"])
    c.set_defaults(func=run_chain)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.key:
        print("ERROR: No key provided. Use --key or set PPA_SHARED_KEY env var.", file=sys.stderr)
        return 2

    try:
        return args.func(args)  # type: ignore[attr-defined]
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected client error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
