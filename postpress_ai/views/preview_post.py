# -*- coding: utf-8 -*-
"""
PostPress AI — Preview Generator (Django)
Absolute Path: /home/techwithwayne/agentsuite/postpress_ai/views/preview_post.py

CHANGE LOG
- 2025-08-23 (Assistant):
  * CHANGED: Hardened preview generator with provider selection (OpenAI/Anthropic),             # CHANGED:
    final-quality override via env or request hints, optional stub path, and strict             # CHANGED:
    JSON contract enforcement.                                                                  # CHANGED:
  * CHANGED: Works with existing wrapper (views.preview) that handles auth/X-PPA-Key.           # CHANGED:
  * CHANGED: Adds robust decoding of varied provider shapes and belts-and-suspenders            # CHANGED:
    contract validation; always returns {title, html, summary}.                                 # CHANGED:

Notes
- Keep Preview fast/cheap with gpt-4o-mini; allow “final” quality (gpt-4.1 / gpt-5-mini)        # CHANGED:
  when requested, *without* touching store code.                                                # CHANGED:
- You must set OPENAI_API_KEY and/or CLAUDE_API_KEY in the *running worker* env, then restart.  # CHANGED:
"""

from __future__ import annotations                                                              # CHANGED:

import html                                                                                     # CHANGED:
import json                                                                                     # CHANGED:
import logging                                                                                  # CHANGED:
import os                                                                                       # CHANGED:
import re                                                                                       # CHANGED:
import threading                                                                                # CHANGED:
from typing import Any, Callable, Dict, Optional                                                # CHANGED:
from urllib.request import Request, urlopen                                                     # CHANGED:
from urllib.error import HTTPError, URLError                                                    # CHANGED:

from django.http import HttpRequest, HttpResponse, JsonResponse                                 # CHANGED:

logger = logging.getLogger(__name__)                                                            # CHANGED:
VERSION = "postpress-ai.v2.1-2025-08-14"                                                        # CHANGED:

# --------------------------------------------------------------------------------------
# JSON helpers (self-contained so we don’t rely on other modules)                         # CHANGED
# --------------------------------------------------------------------------------------

def _json_response(payload: Dict[str, Any], status: int = 200) -> JsonResponse:                 # CHANGED:
    """Return JSON with unicode intact (no ascii-escape)."""                                    # CHANGED:
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})      # CHANGED:

# --------------------------------------------------------------------------------------
# Utilities (sanitize, schema, extraction)                                                # CHANGED
# --------------------------------------------------------------------------------------

def _coerce_str(val: Any) -> str:                                                               # CHANGED:
    try:
        s = str(val or "").strip()
        return re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", s)
    except Exception:
        return ""

def _sanitize_inline(s: str) -> str:                                                            # CHANGED:
    # Not a general sanitizer for HTML bodies; safe for titles/meta lines.                      # CHANGED:
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _build_title(subject: Optional[str], genre: Optional[str], tone: Optional[str]) -> str:      # CHANGED:
    parts = []
    if genre: parts.append(f"[{genre.strip()}]")
    if subject: parts.append(subject.strip())
    if tone: parts.append(f"— {tone.strip()}")
    return " ".join(parts) if parts else "Article — Neutral"

def _preview_json_schema() -> Dict[str, Any]:                                                    # CHANGED:
    """Strict JSON Schema used with providers that support it (OpenAI Responses/Chat)."""       # CHANGED:
    return {
        "name": "postpress_preview",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title":   {"type": "string", "minLength": 1, "maxLength": 200},
                "html":    {"type": "string", "minLength": 1, "maxLength": 100000},
                "summary": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "required": ["title", "html", "summary"],
        },
        "strict": True,
    }

def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:                                 # CHANGED:
    """Try direct JSON, then lax extraction of the first {...} object."""                        # CHANGED:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def _validate_and_fill_contract(obj: Optional[Dict[str, Any]],
                                payload: Dict[str, Any],
                                provider_label: str) -> Dict[str, str]:                          # CHANGED:
    """
    Always return strings for title/html/summary with sane defaults and a provider marker.       # CHANGED:
    """
    out = {"title": "", "html": "", "summary": ""}
    if isinstance(obj, dict):
        for k in ("title", "html", "summary"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()

    if not out["title"]:
        out["title"] = _build_title(
            _coerce_str(payload.get("subject") or payload.get("title")),
            _coerce_str(payload.get("genre")),
            _coerce_str(payload.get("tone")),
        )
    if not out["html"]:
        out["html"] = f"<p>Preview unavailable.</p><!-- provider: {provider_label} -->"
    if "<!-- provider:" not in out["html"]:
        out["html"] = out["html"].rstrip() + f"<!-- provider: {provider_label} -->"
    if not out["summary"]:
        out["summary"] = "Generated preview."
    return out

# --------------------------------------------------------------------------------------
# Provider choice (with final-quality override)                                           # CHANGED
# --------------------------------------------------------------------------------------

_rr_lock = threading.Lock()                                                                    # CHANGED:
_rr_next = 0                                                                                   # CHANGED:

def _truthy_env(name: str) -> bool:                                                            # CHANGED:
    val = (os.getenv(name) or "").strip().lower()
    return val in {"1","true","yes","on"}

def _is_final_request(payload: Dict[str, Any]) -> bool:                                        # CHANGED:
    """
    Treat request as 'final quality' if caller hints publish-quality or env forces it.          # CHANGED:
    Triggers: fields.quality in {'final','publish','high','store'}, fields.tier='final',        # CHANGED:
              fields.mode='publish', or PPA_PREVIEW_FORCE_FINAL=1.                              # CHANGED:
    """
    try:
        q = str(payload.get("quality") or payload.get("tier") or "").strip().lower()
    except Exception:
        q = ""
    mode = str(payload.get("mode") or "").strip().lower()
    if q in {"final","publish","high","store"}: return True
    if mode == "publish": return True
    if _truthy_env("PPA_PREVIEW_FORCE_FINAL"): return True
    return False

def _detect_providers() -> Dict[str, bool]:                                                    # CHANGED:
    have_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
    have_anthropic = bool(os.getenv("CLAUDE_API_KEY", "").strip())
    return {"openai": have_openai, "anthropic": have_anthropic}

def _choose_provider() -> Optional[str]:                                                       # CHANGED:
    avail = _detect_providers()
    pref = (os.getenv("PPA_PREVIEW_PROVIDER") or "").strip().lower()
    strat = (os.getenv("PPA_PREVIEW_STRATEGY") or "").strip().lower()

    if pref in {"openai","anthropic"}:
        return pref if avail.get(pref) else None

    both = avail.get("openai") and avail.get("anthropic")
    if both and (strat == "round_robin" or (pref in ("","auto") and strat == "")):
        global _rr_next
        with _rr_lock:
            chosen = "openai" if (_rr_next % 2 == 0) else "anthropic"
            _rr_next += 1
        return chosen

    return "openai" if avail.get("openai") else ("anthropic" if avail.get("anthropic") else None)

# --------------------------------------------------------------------------------------
# Provider calls (OpenAI / Anthropic)                                                     # CHANGED
# --------------------------------------------------------------------------------------

def _build_user_prompt(payload: Dict[str, Any]) -> str:                                        # CHANGED:
    subject = _coerce_str(payload.get("subject") or payload.get("title"))
    genre = _coerce_str(payload.get("genre") or "Article")
    tone = _coerce_str(payload.get("tone") or "Neutral")
    audience = _coerce_str(payload.get("audience") or payload.get("target") or payload.get("target_audience"))
    keywords = _coerce_str(payload.get("keywords"))
    length = _coerce_str(payload.get("length"))
    cta = _coerce_str(payload.get("cta") or payload.get("call_to_action"))

    parts = [
        f"Subject: {subject or 'n/a'}",
        f"Genre: {genre}",
        f"Tone: {tone}",
        f"Audience: {audience or 'general readers'}",
        f"Keywords: {keywords or 'n/a'}",
        f"Length: {length or 'short'}",
        f"CTA: {cta or 'n/a'}",
        "",
        "Return ONLY a JSON object with keys: title (string), html (string), summary (string).",
        "html should be semantic and production-ready for WordPress (h2/h3, lists, etc.).",
    ]
    return "\n".join(parts)

def _openai_model(final: bool) -> str:                                                         # CHANGED:
    if final:
        return (os.getenv("PPA_PREVIEW_FINAL_OPENAI_MODEL") or "").strip() or "gpt-4.1"
    return (os.getenv("PPA_PREVIEW_OPENAI_MODEL") or "").strip() or "gpt-4o-mini"

def _anthropic_model(final: bool) -> str:                                                      # CHANGED:
    if final:
        return (os.getenv("PPA_PREVIEW_FINAL_ANTHROPIC_MODEL") or "").strip() or "claude-3-5-sonnet-20240620"
    return (os.getenv("PPA_PREVIEW_ANTHROPIC_MODEL") or "").strip() or "claude-sonnet-4-20250514"

def _generate_via_openai(payload: Dict[str, Any]) -> Dict[str, str]:                           # CHANGED:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("openai.missing_key")

    final = _is_final_request(payload)
    model = _openai_model(final)
    url = "https://api.openai.com/v1/chat/completions"

    body = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "You are PostPress AI. Output ONLY strict JSON that matches the provided schema."},
            {"role": "user", "content": f"Build a blog post preview as JSON.\n{_build_user_prompt(payload)}"},
        ],
        "response_format": {  # JSON schema support (structured outputs)
            "type": "json_schema",
            "json_schema": _preview_json_schema(),
        },
        "max_tokens": 1600,
    }

    try:
        req = Request(url,
                      data=json.dumps(body).encode("utf-8"),
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                      method="POST")
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        # Normalize common shapes from OpenAI
        content_text = None
        try:
            content_text = data["choices"][0]["message"]["content"]
        except Exception:
            pass
        if not content_text:
            content_text = data.get("output_text")
        if not content_text:
            out = (data.get("output") or [])
            if out and isinstance(out, list):
                first = out[0]
                blocks = first.get("content") or []
                if blocks and isinstance(blocks, list):
                    blk0 = blocks[0]
                    content_text = (blk0.get("text") or "") if isinstance(blk0, dict) else ""
        obj = _extract_json_object(content_text or "") or {}
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"openai.http_error:{getattr(e, 'code', 'n/a')}")
    except Exception as e:
        raise RuntimeError(f"openai.exception:{e}")

    return _validate_and_fill_contract(obj, payload, provider_label="openai")

def _generate_via_anthropic(payload: Dict[str, Any]) -> Dict[str, str]:                        # CHANGED:
    api_key = os.getenv("CLAUDE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("anthropic.missing_key")

    final = _is_final_request(payload)
    model = _anthropic_model(final)
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": model,
        "max_tokens": 1600,
        "system": "You are PostPress AI. Output ONLY a JSON object with title/html/summary.",
        "messages": [
            {"role": "user", "content": f"Build a blog post preview as JSON.\n{_build_user_prompt(payload)}"},
        ],
    }

    try:
        req = Request(url,
                      data=json.dumps(body).encode("utf-8"),
                      headers=headers,
                      method="POST")
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        # Normalize common shapes from Anthropic
        content_text = None
        try:
            content_text = data["content"][0]["text"]
        except Exception:
            pass
        if not content_text:
            content_text = data.get("output_text")
        if not content_text:
            out = (data.get("output") or [])
            if out and isinstance(out, list):
                first = out[0]
                blocks = first.get("content") or []
                if blocks and isinstance(blocks, list):
                    blk0 = blocks[0]
                    content_text = (blk0.get("text") or "") if isinstance(blk0, dict) else ""
        obj = _extract_json_object(content_text or "") or {}
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"anthropic.http_error:{getattr(e, 'code', 'n/a')}")
    except Exception as e:
        raise RuntimeError(f"anthropic.exception:{e}")

    return _validate_and_fill_contract(obj, payload, provider_label="anthropic")

# --------------------------------------------------------------------------------------
# Loader & entry point                                                                  # CHANGED
# --------------------------------------------------------------------------------------

def _load_service_generator() -> Optional[Callable[[Dict[str, Any]], Dict[str, str]]]:          # CHANGED:
    provider = _choose_provider()
    if provider == "openai":
        return _generate_via_openai
    if provider == "anthropic":
        return _generate_via_anthropic
    return None

def generate_preview(payload: Optional[Dict[str, Any]] = None,
                     service_generator: Optional[Any] = None,
                     request: Optional[Any] = None) -> Dict[str, str]:                           # CHANGED:
    payload = payload or {}
    keys = sorted(list(payload.keys()))
    logger.info("[PPA][preview_post] keys=%s provider_env=%s", keys, os.getenv("PPA_PREVIEW_PROVIDER", ""))

    gen = service_generator if callable(service_generator) else _load_service_generator()

    if callable(gen):
        try:
            return gen(payload)
        except Exception as e:
            logger.warning("[PPA][preview_post] provider error=%s; using local fallback", e)

    # Local safe fallback (contract-stable)
    subject = _coerce_str(payload.get("subject") or payload.get("title"))
    genre = _coerce_str(payload.get("genre"))
    tone = _coerce_str(payload.get("tone"))
    title = _build_title(subject, genre, tone)
    html_out = (
        "<!-- provider: local-fallback -->\n"
        "<article class='ppa-preview'>\n"
        f"  <header>\n"
        f"    <h1>{_sanitize_inline(title)}</h1>\n"
        f"    <p class='ppa-meta'><strong>Genre:</strong> { _sanitize_inline(genre) or '—' } | "
        f"<strong>Tone:</strong> { _sanitize_inline(tone) or '—' }</p>\n"
        f"  </header>\n"
        f"  <p>Preview not available; provider offline.</p>\n"
        f"</article>"
    ).strip()

    return {"title": title, "html": html_out, "summary": "Local fallback preview."}             # CHANGED:

# --------------------------------------------------------------------------------------
# Delegate view used by wrapper (views.preview calls this module)                        # CHANGED
# --------------------------------------------------------------------------------------

def preview(request: HttpRequest) -> JsonResponse | HttpResponse:                               # CHANGED:
    """
    Delegate endpoint used by the public wrapper to generate content via providers.             # CHANGED:
    The outer wrapper performs CORS/auth (X-PPA-Key).                                           # CHANGED:
    """
    try:
        try:
            data = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            data = {}

        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}

        result = generate_preview(fields, request=request)
        result = _validate_and_fill_contract(result, fields, provider_label="delegate")
        payload = {"ok": True, "result": result, "ver": VERSION}
        return _json_response(payload, 200)
    except Exception as exc:
        logger.exception("[PPA][preview_post.delegate][error] %s", exc)
        fallback = {
            "ok": True,
            "result": {
                "title": "PostPress AI Preview (Delegate Error)",
                "html": "<p><em>Preview provider error; please try again.</em></p>",
                "summary": "Fallback preview due to provider error",
            },
            "ver": VERSION,
        }
        return _json_response(fallback, 200)
