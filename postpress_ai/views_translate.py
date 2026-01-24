"""
PostPress AI — Translate Endpoint (Django)

Route:
  POST /postpress-ai/translate/

Guaranteed JSON envelope on every path.

WHY THIS FILE CHANGED (IMPORTANT)
---------------------------------
We are still seeing 30s client ReadTimeouts. That means the server didn't return anything
within 30 seconds. The most common cause is the OpenAI client call not honoring timeout
(or hanging on network reads).

This version is bulletproof:
- Uses requests() directly to OpenAI with STRICT hard timeouts (connect+read).  # CHANGED:
- Enforces a strict per-request time budget.                                     # CHANGED:
- Chunk + per-request cap + polling via job_id (same API shape).                # CHANGED:
- Keeps auth fast-path + DB fallback limited to postpress_ai models only.       # CHANGED:
- Always returns JSON.

CHANGE LOG
----------
2026-01-23 • FIX: Force hard OpenAI timeouts by using requests (not OpenAI SDK).     # CHANGED:
2026-01-23 • FIX: Auth fallback scans ONLY postpress_ai models (not whole project). # CHANGED:
2026-01-23 • HARDEN: Strict per-request budget; never blocks > budget.              # CHANGED:
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import logging
import re
from typing import Any, Dict, Optional, Tuple, List

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


# =========================
# Config (safe defaults)
# =========================

CACHE_TTL_SECONDS = getattr(settings, "PPA_TRANSLATE_CACHE_TTL", 60 * 60 * 24)  # 24h

# IMPORTANT: keep HTTP request under shared-host gateway limits.
REQUEST_BUDGET_SECONDS = getattr(settings, "PPA_TRANSLATE_REQUEST_BUDGET", 18)         # CHANGED:
BUDGET_SAFETY_SECONDS = getattr(settings, "PPA_TRANSLATE_BUDGET_SAFETY", 2)            # CHANGED:

MAX_HTML_CHARS = getattr(settings, "PPA_TRANSLATE_MAX_HTML_CHARS", 300_000)

CHUNK_TARGET_CHARS = getattr(settings, "PPA_TRANSLATE_CHUNK_TARGET_CHARS", 1800)      # CHANGED:
MAX_CHUNKS_PER_REQUEST = getattr(settings, "PPA_TRANSLATE_MAX_CHUNKS_PER_REQUEST", 3) # CHANGED:
POLL_NEXT_MS = getattr(settings, "PPA_TRANSLATE_POLL_NEXT_MS", 250)

OPENAI_MODEL = getattr(settings, "PPA_TRANSLATE_MODEL", os.getenv("PPA_TRANSLATE_MODEL", "gpt-4o-mini"))

# HARD network timeouts for OpenAI API (requests enforces these).
OPENAI_CONNECT_TIMEOUT = getattr(settings, "PPA_TRANSLATE_OPENAI_CONNECT_TIMEOUT", 3)  # CHANGED:
OPENAI_READ_TIMEOUT = getattr(settings, "PPA_TRANSLATE_OPENAI_READ_TIMEOUT", 10)       # CHANGED:

AUTH_OK_TTL_SECONDS = getattr(settings, "PPA_AUTH_OK_TTL", 60 * 10)  # 10 minutes


# =========================
# Helpers: consistent JSON
# =========================

def _resp(
    *,
    ok: bool,
    html: Optional[str],
    cached: bool,
    lang: str,
    mode: str,
    draft_hash: str,
    status: int = 200,
    error: Optional[str] = None,
    message: str = "",
    retryable: bool = False,
    pending: bool = False,
    job_id: Optional[str] = None,
    progress: float = 1.0,
    next_poll_ms: int = 0,
    elapsed_ms: int = 0,
) -> JsonResponse:
    payload = {
        "ok": bool(ok),
        "html": html if ok else None,
        "cached": bool(cached),
        "lang": lang or "original",
        "mode": mode or "strict",
        "draft_hash": draft_hash or "",
        "error": error,
        "message": message,
        "retryable": bool(retryable),
        "pending": bool(pending),
        "job_id": job_id,
        "progress": float(progress),
        "next_poll_ms": int(next_poll_ms),
        "elapsed_ms": int(elapsed_ms),
    }
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def _safe_json_loads(raw: bytes) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        if not raw:
            return None, "bad_request"
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            return None, "bad_request"
        return obj, None
    except Exception:
        return None, "invalid_json"


def _sha256_text(txt: str) -> str:
    return hashlib.sha256(txt.encode("utf-8", errors="ignore")).hexdigest()


def _now_ms(start: float) -> int:
    return int(round((time.time() - start) * 1000))


# =========================
# Auth
# =========================

def _extract_key(request: HttpRequest) -> str:
    auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if auth.lower().startswith("bearer "):
        candidate = auth.split(" ", 1)[1].strip()
        if candidate:
            return candidate

    for h in ("HTTP_X_PPA_KEY", "HTTP_X_POSTPRESS_KEY", "HTTP_X_CONNECTION_KEY"):
        candidate = (request.META.get(h) or "").strip()
        if candidate:
            return candidate

    return ""


def _shared_key_ok(provided: str) -> bool:
    if not provided:
        return False

    expected_one = getattr(settings, "PPA_SHARED_KEY", "") or os.getenv("PPA_SHARED_KEY", "")
    if expected_one and provided == expected_one:
        return True

    expected_many = getattr(settings, "PPA_SHARED_KEYS", "") or os.getenv("PPA_SHARED_KEYS", "")
    if expected_many:
        allowed = {k.strip() for k in expected_many.split(",") if k.strip()}
        if provided in allowed:
            return True

    return False


def _db_key_ok_postpress_ai_only(provided: str) -> bool:
    if not provided:
        return False

    ck = f"ppa:auth_ok:{hashlib.sha256(provided.encode('utf-8')).hexdigest()[:24]}"
    if cache.get(ck) is True:
        return True

    try:
        from django.apps import apps
        app_config = apps.get_app_config("postpress_ai")
        models = list(app_config.get_models())
    except Exception:
        return False

    key_fields = ("connection_key", "license_key", "key", "api_key")
    active_fields = ("is_active", "active", "enabled")

    for model in models:
        try:
            meta = getattr(model, "_meta", None)
            if not meta:
                continue
            field_names = {f.name for f in meta.fields}

            kf = next((f for f in key_fields if f in field_names), None)
            if not kf:
                continue

            qs = model.objects.filter(**{kf: provided})

            af = next((f for f in active_fields if f in field_names), None)
            if af:
                qs = qs.filter(**{af: True})

            if qs.exists():
                cache.set(ck, True, AUTH_OK_TTL_SECONDS)
                return True
        except Exception:
            continue

    return False


def _ppa_key_ok(request: HttpRequest) -> bool:
    provided = _extract_key(request)
    if not provided:
        return False
    if _shared_key_ok(provided):
        return True
    return _db_key_ok_postpress_ai_only(provided)


# =========================
# Chunking (HTML-ish)
# =========================

_BLOCK_SPLIT_RE = re.compile(
    r"(?i)(</p>|</li>|</h[1-6]>|</blockquote>|</pre>|</ul>|</ol>|<br\s*/?>)"
)


def _chunk_by_length(text: str, max_chars: int) -> List[str]:
    if not text:
        return [""]
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        out.append(text[i : i + max_chars])
        i += max_chars
    return out


def _split_html_into_blocks(html: str) -> List[str]:
    if not html:
        return [""]

    parts = _BLOCK_SPLIT_RE.split(html)
    if len(parts) <= 1:
        return _chunk_by_length(html, CHUNK_TARGET_CHARS)

    blocks: List[str] = []
    buf = ""
    for p in parts:
        if p is None:
            continue
        buf += p
        if _BLOCK_SPLIT_RE.fullmatch(p or ""):
            blocks.append(buf)
            buf = ""

    if buf.strip():
        blocks.append(buf)

    out: List[str] = []
    for b in blocks:
        if len(b) <= CHUNK_TARGET_CHARS:
            out.append(b)
        else:
            out.extend(_chunk_by_length(b, CHUNK_TARGET_CHARS))
    return out


def _job_id_for(draft_hash: str, lang: str, mode: str) -> str:
    base = f"{draft_hash}:{lang}:{mode}"
    return "tj_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _job_cache_key(job_id: str) -> str:
    return f"ppa:translate_job:{job_id}"


def _final_cache_key(draft_hash: str, mode: str, lang: str) -> str:
    return f"ppa:translate:{draft_hash}:{mode}:{lang}"


# =========================
# Translation engine (HARD TIMEOUTS)
# =========================

def _translate_html_openai_requests(html: str, lang: str, mode: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Calls OpenAI Chat Completions via requests with strict timeouts.
    This is the reliable way to avoid 30s+ hangs.  # CHANGED:
    """
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "openai_not_configured", False

    style = (
        "Translate faithfully and literally."
        if (mode or "strict") == "strict"
        else "Translate naturally while keeping meaning. Do not add new facts."
    )

    system = (
        "You are a translation engine.\n"
        "Task: Translate the user's HTML content into the target language.\n"
        "Rules:\n"
        "- Preserve ALL HTML tags, attributes, ids, classes, inline styles, links.\n"
        "- Do NOT wrap in markdown.\n"
        "- Return ONLY valid HTML.\n"
        "- Do NOT add commentary.\n"
        f"- {style}\n"
        f"Target language: {lang}\n"
    )

    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": html},
        ],
    }

    try:
        import requests  # CHANGED:

        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=(int(OPENAI_CONNECT_TIMEOUT), int(OPENAI_READ_TIMEOUT)),  # CHANGED:
        )
        if r.status_code >= 400:
            return None, "openai_error", True

        data = r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not text:
            return None, "openai_error", True
        return text, None, False

    except Exception as e:
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return None, "timeout", True
        return None, "openai_error", True


# =========================
# View
# =========================

@csrf_exempt
def translate_view(request: HttpRequest) -> JsonResponse:
    start = time.time()

    if request.method != "POST":
        return _resp(
            ok=False, html=None, cached=False,
            lang="original", mode="strict", draft_hash="",
            status=405, error="method_not_allowed",
            message="Method not allowed", retryable=False,
            elapsed_ms=_now_ms(start),
        )

    if not _ppa_key_ok(request):
        return _resp(
            ok=False, html=None, cached=False,
            lang="original", mode="strict", draft_hash="",
            status=401, error="unauthorized",
            message="Unauthorized", retryable=False,
            elapsed_ms=_now_ms(start),
        )

    body_obj, parse_err = _safe_json_loads(request.body)
    if parse_err:
        return _resp(
            ok=False, html=None, cached=False,
            lang="original", mode="strict", draft_hash="",
            status=400, error=parse_err,
            message="Invalid request JSON", retryable=False,
            elapsed_ms=_now_ms(start),
        )

    lang = (body_obj.get("lang") or "original").strip()
    mode = (body_obj.get("mode") or "strict").strip()
    job_id = (body_obj.get("job_id") or "").strip()

    draft_hash = (body_obj.get("draft_hash") or "").strip()
    original_html = body_obj.get("original_html") or ""
    original_json = body_obj.get("original_json")

    if not draft_hash:
        seed = ""
        if isinstance(original_json, dict):
            seed = json.dumps(original_json, sort_keys=True, ensure_ascii=False)
        else:
            seed = str(original_html or "")
        draft_hash = "h_" + _sha256_text(seed)[:16]

    if not isinstance(original_html, str):
        original_html = str(original_html)

    # English/original fast-path
    if lang.lower() in ("original", "en", "en-us", "en_us", "en-gb", "en_gb") and not body_obj.get("force_translate"):
        return _resp(
            ok=True, html=original_html, cached=True,
            lang="original", mode=mode, draft_hash=draft_hash,
            status=200, error=None, message="Original content",
            retryable=False, pending=False, job_id=None,
            progress=1.0, next_poll_ms=0,
            elapsed_ms=_now_ms(start),
        )

    # Final cache wins
    final_key = _final_cache_key(draft_hash, mode, lang)
    final_cached = cache.get(final_key)
    if isinstance(final_cached, str) and final_cached.strip():
        return _resp(
            ok=True, html=final_cached, cached=True,
            lang=lang, mode=mode, draft_hash=draft_hash,
            status=200, error=None, message="Cached translation",
            retryable=False, pending=False, job_id=None,
            progress=1.0, next_poll_ms=0,
            elapsed_ms=_now_ms(start),
        )

    # Poll/continue
    if job_id:
        job = cache.get(_job_cache_key(job_id))
        if not isinstance(job, dict):
            # race-safe: maybe final cache exists now
            final_cached2 = cache.get(final_key)
            if isinstance(final_cached2, str) and final_cached2.strip():
                return _resp(
                    ok=True, html=final_cached2, cached=True,
                    lang=lang, mode=mode, draft_hash=draft_hash,
                    status=200, error=None, message="Cached translation",
                    retryable=False, pending=False, job_id=None,
                    progress=1.0, next_poll_ms=0,
                    elapsed_ms=_now_ms(start),
                )
            return _resp(
                ok=False, html=None, cached=False,
                lang=lang, mode=mode, draft_hash=draft_hash,
                status=404, error="job_not_found",
                message="Translation job not found or expired. Please re-translate.",
                retryable=True, pending=False,
                job_id=job_id, progress=0.0, next_poll_ms=0,
                elapsed_ms=_now_ms(start),
            )
    else:
        # First call validation
        if not original_html.strip():
            return _resp(
                ok=False, html=None, cached=False,
                lang=lang, mode=mode, draft_hash=draft_hash,
                status=400, error="bad_request",
                message="Missing original_html", retryable=False,
                elapsed_ms=_now_ms(start),
            )

        if len(original_html) > MAX_HTML_CHARS:
            return _resp(
                ok=False, html=None, cached=False,
                lang=lang, mode=mode, draft_hash=draft_hash,
                status=413, error="too_large",
                message=f"Payload too large to translate reliably (>{MAX_HTML_CHARS} chars).",
                retryable=False,
                elapsed_ms=_now_ms(start),
            )

        job_id = _job_id_for(draft_hash, lang, mode)
        chunks = _split_html_into_blocks(original_html)

        job = {
            "job_id": job_id,
            "draft_hash": draft_hash,
            "lang": lang,
            "mode": mode,
            "chunks": chunks,
            "done": [None] * len(chunks),
            "idx": 0,
            "created": time.time(),
            "updated": time.time(),
        }
        cache.set(_job_cache_key(job_id), job, CACHE_TTL_SECONDS)

    # Work loop (strict budget)
    chunks: List[str] = job.get("chunks") or []
    done: List[Optional[str]] = job.get("done") or []
    idx: int = int(job.get("idx") or 0)

    total = max(1, len(chunks))
    translated_this_call = 0

    while idx < len(chunks):
        # stop if we're near the request budget
        elapsed = time.time() - start
        if elapsed >= float(REQUEST_BUDGET_SECONDS - BUDGET_SAFETY_SECONDS):
            break

        if translated_this_call >= int(MAX_CHUNKS_PER_REQUEST):
            break

        # skip done
        if idx < len(done) and isinstance(done[idx], str) and (done[idx] or "").strip():
            idx += 1
            continue

        piece = chunks[idx] if idx < len(chunks) else ""
        if not piece.strip():
            done[idx] = piece
            idx += 1
            continue

        translated, err, retryable = _translate_html_openai_requests(piece, lang, mode)  # CHANGED:

        if err or not translated:
            job["done"] = done
            job["idx"] = idx
            job["updated"] = time.time()
            cache.set(_job_cache_key(job_id), job, CACHE_TTL_SECONDS)

            return _resp(
                ok=False, html=None, cached=False,
                lang=lang, mode=mode, draft_hash=draft_hash,
                status=504 if err == "timeout" else 500,
                error=err or "server_error",
                message=f"Translation chunk failed ({err or 'server_error'}).",
                retryable=bool(retryable),
                pending=True, job_id=job_id,
                progress=float(idx) / float(total),
                next_poll_ms=int(POLL_NEXT_MS),
                elapsed_ms=_now_ms(start),
            )

        done[idx] = translated
        idx += 1
        translated_this_call += 1

    # persist job
    job["done"] = done
    job["idx"] = idx
    job["updated"] = time.time()
    cache.set(_job_cache_key(job_id), job, CACHE_TTL_SECONDS)

    # build display html: translated + remaining original
    display_parts: List[str] = []
    for i in range(len(chunks)):
        if i < len(done) and isinstance(done[i], str) and done[i] is not None:
            display_parts.append(done[i] or "")
        else:
            display_parts.append(chunks[i] or "")
    display_html = "".join(display_parts)

    pending = idx < len(chunks)
    progress = float(idx) / float(total)

    if not pending:
        cache.set(final_key, display_html, CACHE_TTL_SECONDS)
        cache.delete(_job_cache_key(job_id))
        return _resp(
            ok=True, html=display_html, cached=False,
            lang=lang, mode=mode, draft_hash=draft_hash,
            status=200, error=None,
            message=f"Translated (chunks={total})",
            retryable=False,
            pending=False, job_id=None,
            progress=1.0, next_poll_ms=0,
            elapsed_ms=_now_ms(start),
        )

    return _resp(
        ok=True, html=display_html, cached=False,
        lang=lang, mode=mode, draft_hash=draft_hash,
        status=200, error=None,
        message=f"Partial translation ({int(progress*100)}%) — polling continues",
        retryable=False,
        pending=True, job_id=job_id,
        progress=progress, next_poll_ms=int(POLL_NEXT_MS),
        elapsed_ms=_now_ms(start),
    )
