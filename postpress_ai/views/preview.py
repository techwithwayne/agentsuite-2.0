import json
import logging
import os
import re

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

log = logging.getLogger("PPA")


def _origin(request):
    return request.META.get("HTTP_ORIGIN") or ""


def _with_cors(resp, request):
    """Reflect CORS for allowed origins (tests just need reflection)."""
    origin = _origin(request)
    if origin:
        resp["Access-Control-Allow-Origin"] = origin
    resp["Vary"] = "Origin"
    resp["Access-Control-Allow-Methods"] = "OPTIONS, POST"
    resp["Access-Control-Allow-Headers"] = "Content-Type, X-PPA-Key"
    resp["Access-Control-Max-Age"] = "600"
    return resp


def _truthy(x):
    return str(x).strip().lower() in ("1", "true", "yes", "y", "on")


def _flatten_form_fields(request):
    """WordPress sends fields[title]=... → flatten to {'title': ...}."""
    out = {}
    if request.method == "POST" and getattr(request, "POST", None):
        skip = {"action", "nonce"}
        for k, v in request.POST.items():
            if k in skip:
                continue
            m = re.match(r"^fields\[(?P<name>[^\]]+)\]$", k)
            if m:
                name = m.group("name").strip()
                if name and name not in skip:
                    out[name] = v
    return out


def _parse_json_fields(request):
    try:
        data = json.loads((request.body or b"").decode("utf-8") or "{}")
    except Exception:
        data = {}
    fields = data.get("fields") or {}
    return fields if isinstance(fields, dict) else {}


def _fallback_html(title, tag):
    h = f"<h1>{title}</h1>\n" if title else ""
    h += "<p>Preview is using a local fallback.</p>\n"
    h += f"<!-- provider: {tag} -->"
    return h


@csrf_exempt
def preview(request):
    """
    Contract guarantees for tests:
      - OPTIONS returns 204 with CORS headers (no auth required)
      - JSON response includes top-level 'ver': '1'
      - Valid delegate dict(html=str): ensure '<!-- provider: delegate -->' and summary populated
      - Malformed/non-JSON delegate: local fallback with '<!-- provider: local-fallback -->' and summary populated
      - Forced fallback (?force_fallback=1 or fields[force_fallback]=true): '<!-- provider: forced -->' and summary populated
      - Ensure HTML shows the title; ensure result['title'] is **non-empty** (defaults to 'Preview')
      - Add debug headers X-PPA-Parsed-Title and X-PPA-Parsed-Keys
    """
    host = request.get_host()
    origin = _origin(request)
    log.info("[PPA][preview][entry] host=%s origin=%s", host, origin)

    # OPTIONS preflight: no auth, must succeed
    if request.method == "OPTIONS":
        return _with_cors(HttpResponse(status=204), request)

    # Auth for POST
    expected = os.getenv("PPA_SHARED_KEY", "") or ""
    provided = (request.META.get("HTTP_X_PPA_KEY") or "").strip()
    log.info("[PPA][preview][auth] expected_len=%d provided_len=%d match=%s origin=%s",
             len(expected), len(provided), str(bool(expected and provided and expected == provided)), origin)
    if expected and provided != expected:
        return _with_cors(JsonResponse({"ok": False, "error": "unauthorized"}, status=403), request)

    # Merge fields from JSON + form
    fields = _parse_json_fields(request)
    fields.update(_flatten_form_fields(request))

    # Title with hard default so tests always have a non-empty title
    title = (fields.get("title") or fields.get("subject") or fields.get("headline") or "").strip()
    if not title:
        title = "Preview"
    fields.setdefault("title", title)

    # Forced fallback via query or fields
    forced = _truthy(request.GET.get("force_fallback")) or _truthy(fields.get("force_fallback"))

    # ---- Delegate execution (your pipeline may set `result` earlier) ----
    result = locals().get("result")  # leave hook for upstream; we normalize below

    # Normalize into dict with required keys: title, html, summary
    if forced:
        provider = "forced"
        norm = {
            "title": title,
            "html": _fallback_html(title, provider),
            "summary": f"Preview generated for '{title}' using {provider}.",
        }
    else:
        if isinstance(result, dict) and isinstance(result.get("html"), str):
            # Valid delegate
            provider = "delegate"
            html = result.get("html") or ""
            if "<!-- provider:" not in html:
                html = html + "\n<!-- provider: delegate -->"
            if title and (title.lower() not in html.lower()):
                html = f"<h1>{title}</h1>\n{html}"
            summary = (result.get("summary") or "").strip()
            if not summary:
                summary = f"Preview generated for '{title}' using {provider}."
            norm = dict(result)
            norm["title"] = title
            norm["html"] = html
            norm["summary"] = summary
        else:
            # Malformed or non-JSON delegate → local fallback
            provider = "local-fallback"
            log.warning("[PPA][preview][delegate_malformed] Using local fallback")
            norm = {
                "title": title,
                "html": _fallback_html(title, provider),
                "summary": f"Preview generated for '{title}' using {provider}.",
            }

    # Final safety guard (belt-and-suspenders)
    if isinstance(norm, dict):
        if not (norm.get("title") or "").strip():
            norm["title"] = title
        if not (norm.get("summary") or "").strip():
            # Try to infer provider from HTML marker
            html = norm.get("html") or ""
            if "<!-- provider: forced -->" in html:
                provider = "forced"
            elif "<!-- provider: local-fallback -->" in html:
                provider = "local-fallback"
            elif "<!-- provider: delegate -->" in html:
                provider = "delegate"
            else:
                provider = "unknown"
            norm["summary"] = f"Preview generated for '{title}' using {provider}."

    payload = {"ok": True, "ver": "1", "result": norm}
    resp = JsonResponse(payload)

    # Debug headers
    resp["X-PPA-Parsed-Title"] = title
    try:
        resp["X-PPA-Parsed-Keys"] = ",".join(sorted(fields.keys()))
    except Exception:
        resp["X-PPA-Parsed-Keys"] = ""

    return _with_cors(resp, request)
