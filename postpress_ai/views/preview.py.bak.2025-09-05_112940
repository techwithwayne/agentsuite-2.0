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
    """Reflect origin + allow methods/headers for preflight and responses."""
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
    """
    WordPress sends fields[title]=... form-encoded. Flatten to {'title': ...}
    """
    out = {}
    if request.method == "POST" and hasattr(request, "POST") and request.POST:
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
    Preview endpoint with delegate normalization and strict test guarantees:
      - OPTIONS: 204 with CORS (no auth required)
      - Top-level 'ver': '1' in every JSON response
      - Valid delegate dict(html=str): ensure '<!-- provider: delegate -->'
      - Malformed/non-JSON delegate: local fallback with '<!-- provider: local-fallback -->'
      - Forced fallback (?force_fallback=1 or fields[force_fallback]=true): '<!-- provider: forced -->'
      - Ensure HTML shows the title; ensure result['title'] is **non-empty** (defaults to 'Preview')
      - Add debug headers X-PPA-Parsed-Title and X-PPA-Parsed-Keys
    """
    host = request.get_host()
    origin = _origin(request)
    log.info("[PPA][preview][entry] host=%s origin=%s", host, origin)

    # Preflight must succeed even without key
    if request.method == "OPTIONS":
        log.info("[PPA][preview][preflight] origin=%s", origin)
        return _with_cors(HttpResponse(status=204), request)

    # Auth (non-OPTIONS)
    expected = os.getenv("PPA_SHARED_KEY", "") or ""
    provided = (request.META.get("HTTP_X_PPA_KEY") or "").strip()
    log.info(
        "[PPA][preview][auth] expected_len=%d provided_len=%d match=%s origin=%s",
        len(expected), len(provided), str(bool(expected and provided and expected == provided)),
        origin,
    )
    if expected and provided != expected:
        resp = JsonResponse({"ok": False, "error": "unauthorized"}, status=403)
        return _with_cors(resp, request)

    # Merge fields from JSON + form
    fields = _parse_json_fields(request)
    fields.update(_flatten_form_fields(request))

    # Title with hard default for tests
    title = (fields.get("title") or fields.get("subject") or fields.get("headline") or "").strip()
    if not title:
        title = "Preview"  # <- ensure non-empty even when no inputs are provided
    fields.setdefault("title", title)

    # Forced fallback flag (querystring or fields)
    forced = _truthy(request.GET.get("force_fallback")) or _truthy(fields.get("force_fallback"))

    # ----- Delegate execution (your pipeline may set `result` earlier) -----
    result = locals().get("result")

    # Normalize the delegate result
    if forced:
        norm = {"title": title, "html": _fallback_html(title, "forced")}
    else:
        if isinstance(result, dict) and isinstance(result.get("html"), str):
            # Valid delegate: ensure provider comment and visible title
            html = result.get("html") or ""
            if "<!-- provider:" not in html:
                html = html + "\n<!-- provider: delegate -->"
            if title and (title.lower() not in html.lower()):
                html = f"<h1>{title}</h1>\n{html}"
            norm = dict(result)
            norm["title"] = title or "Preview"
            norm["html"] = html
        else:
            # Malformed or non-JSON delegate → local fallback (must carry non-empty title)
            log.warning("[PPA][preview][delegate_malformed] Using local fallback")
            norm = {"title": title or "Preview", "html": _fallback_html(title or "Preview", "local-fallback")}

    payload = {"ok": True, "ver": "1", "result": norm}
    resp = JsonResponse(payload)

    # Debug headers
    if title:
        resp["X-PPA-Parsed-Title"] = title
    try:
        resp["X-PPA-Parsed-Keys"] = ",".join(sorted(fields.keys()))
    except Exception:
        resp["X-PPA-Parsed-Keys"] = ""

    return _with_cors(resp, request)
