# /home/techwithwayne/agentsuite/postpress_ai/views/preview_post.py
# -*- coding: utf-8 -*-
"""
PostPress AI — Preview Generator (Django)

========= CHANGE LOG =========
2026-01-22: ENFORCE: Genre/Tone (and Word Count/Audience/Brief) are now translated into hard style rules.  # CHANGED:
           - Genre controls structure; Tone controls voice; both must be satisfied together.             # CHANGED:
           - Adds a compliance checklist so outputs stop defaulting to generic “helpful guide”.          # CHANGED:
           - Normalizes keywords + word_count inputs from WP payload.                                   # CHANGED:
           - Adds rule: HTML should avoid duplicating the title as an H1 inside the body.               # CHANGED:

2026-01-25: ADD: Usage accounting (token tracking) for OpenAI + Anthropic preview generation.            # CHANGED:
           - Extracts provider usage tokens deterministically.                                           # CHANGED:
           - Atomically increments an existing License usage field if present (no migrations here).     # CHANGED:
           - Uses a request/thread-local context to avoid polluting provider prompts with secrets.       # CHANGED:
           - Never logs raw license keys.                                                                # CHANGED:

2026-01-25: FIX: If preview requests don’t include license_key, derive it via Activation using site_url. # CHANGED:
           - Normalizes site_url deterministically to match Activation normalization.                    # CHANGED:
           - Records token usage against the resolved License key.                                      # CHANGED:

2026-01-25: FIX: NULL-safe token increments so “0 used” actually moves.                                  # CHANGED:
           - Use Coalesce(F(field), 0) + total (SQL NULL-safe).                                          # CHANGED:
           - Add Origin/Referer fallback to recover site_url for Activation lookup.                      # CHANGED:
           - Improve usage-field detection ranking (still best-effort).                                  # CHANGED:

2026-01-25: FIX: Markdown leak prevention for “Extra instructions” + output HTML.                         # CHANGED:
           - Demote Markdown from user-provided instructions before sending to provider.                 # CHANGED:
           - Hard-ban Markdown in the prompt contract (links must be <a href="...">).                    # CHANGED:
           - Post-sanitize provider output to convert Markdown links to HTML anchors (failsafe).         # CHANGED:

2026-01-25: HARDEN: Handle escaped Markdown tokens from WP/JSON (users don’t type backslashes).           # CHANGED:
           - Convert \[Text\]\(url\) and \[Text\](url) into HTML anchors.                                 # CHANGED:
           - Linkify naked URLs/domains (google.com, www.google.com, https://...).                       # CHANGED:

2026-01-26: ADD: Write UsageEvent ledger rows when usage tokens are available (primary source of truth).  # CHANGED:
           - Best-effort schema introspection to avoid tight coupling and avoid breaking deployments.     # CHANGED:
           - If UsageEvent write succeeds, skip legacy License-field increment (prevents double count).  # CHANGED:
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
from typing import Any, Callable, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse  # CHANGED:

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.db import models  # CHANGED:
from django.db.models import F  # CHANGED:
from django.db.models.functions import Coalesce  # CHANGED:

logger = logging.getLogger(__name__)
VERSION = "postpress-ai.v2.1-2025-08-14"

# --------------------------------------------------------------------------------------
# Request context (thread-local)
# --------------------------------------------------------------------------------------

# CHANGED:
# We need access to the license_key/site_url for usage accounting, but we must NOT
# add these into the provider prompt payload. Thread-local keeps it per-request.
_ctx = threading.local()


def _mask_key_for_log(key: str) -> str:  # CHANGED:
    if not key:
        return ""
    k = str(key).strip()
    if len(k) <= 8:
        return "*" * len(k)
    return f"{k[:4]}…{k[-4:]}"


def _ctx_set(license_key: str = "", site_url: str = "") -> None:  # CHANGED:
    _ctx.license_key = str(license_key or "").strip()
    _ctx.site_url = str(site_url or "").strip()


def _ctx_get_license_key() -> str:  # CHANGED:
    try:
        return str(getattr(_ctx, "license_key", "") or "").strip()
    except Exception:
        return ""


def _ctx_get_site_url() -> str:  # CHANGED:
    try:
        return str(getattr(_ctx, "site_url", "") or "").strip()
    except Exception:
        return ""


def _ctx_clear() -> None:  # CHANGED:
    try:
        if hasattr(_ctx, "license_key"):
            delattr(_ctx, "license_key")
        if hasattr(_ctx, "site_url"):
            delattr(_ctx, "site_url")
    except Exception:
        pass


def _normalize_site_url_for_lookup(raw: str) -> str:  # CHANGED:
    """
    Normalize site_url to match Activation normalization:
    - require http(s) if parseable
    - lower-case host
    - drop path/query/fragment
    - drop trailing slash
    - keep port if present
    - return scheme://host[:port]
    """
    s = str(raw or "").strip()
    if not s:
        return ""

    # Prefer Activation.normalize_site_url if present (single source of truth)
    try:
        from postpress_ai.models.activation import Activation  # local import
        model_norm = getattr(Activation, "normalize_site_url", None)
        if callable(model_norm):
            out = model_norm(s)
            out = str(out or "").strip()
            return out
    except Exception:
        # Fall through to deterministic normalization below
        pass

    try:
        parsed = urlparse(s)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return s.rstrip("/")
        host = parsed.hostname.lower()
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}".rstrip("/")
    except Exception:
        return s.rstrip("/")


def _derive_license_key_from_site(site_url: str) -> str:  # CHANGED:
    """
    Derive license_key using Activation(site_url) -> Activation.license.key.

    This is the bulletproof path when preview calls don't include license_key.
    """
    norm_site = _normalize_site_url_for_lookup(site_url)
    if not norm_site:
        return ""

    try:
        from postpress_ai.models.activation import Activation
        act = (
            Activation.objects.select_related("license")
            .filter(site_url=norm_site)
            .first()
        )
        if not act or not getattr(act, "license", None):
            return ""
        key = getattr(act.license, "key", "") or ""
        return str(key).strip()
    except Exception:
        logger.exception("[PPA][preview_post][usage] derive_license_failed site=%s", norm_site)
        return ""


# --------------------------------------------------------------------------------------
# JSON helpers
# --------------------------------------------------------------------------------------

def _json_response(payload: Dict[str, Any], status: int = 200) -> JsonResponse:
    """Return JSON with unicode intact (no ascii-escape)."""
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

def _coerce_str(val: Any) -> str:
    try:
        s = str(val or "").strip()
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    except Exception:
        return ""


def _sanitize_inline(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# --------------------------------------------------------------------------------------
# CHANGED: Markdown detectors/converters (failsafe for “Extra instructions” + model output)
# --------------------------------------------------------------------------------------

_MD_ESCAPE_RE = re.compile(r"\\([\[\]\(\)`*_])")  # CHANGED:


def _unescape_md_escapes(s: str) -> str:  # CHANGED:
    """Turn \[ \] \( \) \` \* \_ into literal characters."""
    t = str(s or "")
    if not t:
        return ""
    t = _MD_ESCAPE_RE.sub(r"\1", t)
    t = _MD_ESCAPE_RE.sub(r"\1", t)
    return t


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")  # CHANGED:

_BARE_URL_RE = re.compile(
    r"\b(?:https?://[^\s<>'\"()]+|www\.[^\s<>'\"()]+|[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s<>'\"()]*)?)\b",
    flags=re.I,
)  # CHANGED:
_DOMAIN_LIKE_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}(:\d+)?(?:/.*)?$", flags=re.I)  # CHANGED:
_URL_TRAIL_PUNCT = ".,);:!?]}>"  # CHANGED:


def _href_from_url_like(url: str) -> str:  # CHANGED:
    u = str(url or "").strip()
    if not u:
        return ""
    if re.match(r"^https?://", u, flags=re.I):
        return u
    if u.lower().startswith("www."):
        return f"https://{u}"
    if _DOMAIN_LIKE_RE.match(u):
        return f"https://{u}"
    return ""


def _split_url_trailing_punct(token: str) -> tuple[str, str]:  # CHANGED:
    u = str(token or "")
    trail = ""
    while u and u[-1] in _URL_TRAIL_PUNCT:
        trail = u[-1] + trail
        u = u[:-1]
    return u, trail


def _is_inside_html_tag(s: str, idx: int) -> bool:  # CHANGED:
    try:
        last_lt = s.rfind("<", 0, idx)
        last_gt = s.rfind(">", 0, idx)
        return last_lt > last_gt
    except Exception:
        return False


def _is_inside_anchor(s: str, idx: int) -> bool:  # CHANGED:
    try:
        low = s.lower()
        last_open = low.rfind("<a", 0, idx)
        if last_open == -1:
            return False
        last_close = low.rfind("</a", 0, idx)
        if last_close > last_open:
            return False
        open_end = low.find(">", last_open)
        if open_end == -1 or open_end > idx:
            return False
        return True
    except Exception:
        return False


def _linkify_bare_urls_htmlish(s: str) -> str:  # CHANGED:
    t = str(s or "")
    if not t:
        return ""

    out: list[str] = []
    last = 0
    for m in _BARE_URL_RE.finditer(t):
        start, end = m.span()
        token = m.group(0) or ""
        out.append(t[last:start])

        if _is_inside_html_tag(t, start) or _is_inside_anchor(t, start):
            out.append(t[start:end])
            last = end
            continue

        raw_url, trail = _split_url_trailing_punct(token)
        href = _href_from_url_like(raw_url)
        if not href:
            out.append(t[start:end])
            last = end
            continue

        href_esc = html.escape(href, quote=True)
        text_esc = html.escape(raw_url, quote=False)
        out.append(f'<a href="{href_esc}" target="_blank" rel="nofollow noopener">{text_esc}</a>{trail}')
        last = end

    out.append(t[last:])
    return "".join(out)


def _demote_markdown_text(s: str) -> str:  # CHANGED:
    t = str(s or "")
    if not t:
        return ""
    t = _unescape_md_escapes(t)  # CHANGED:
    t = t.replace("```", "")  # CHANGED:
    t = re.sub(r"`([^`]+)`", r"\1", t)  # CHANGED:
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)  # CHANGED:
    t = _MD_LINK_RE.sub(lambda m: f"{(m.group(1) or '').strip()} ({(m.group(2) or '').strip()})", t)  # CHANGED:
    return _sanitize_inline(t)  # CHANGED:


def _sanitize_html_output(s: str) -> str:  # CHANGED:
    t = str(s or "").strip()
    if not t:
        return ""

    t = _unescape_md_escapes(t)  # CHANGED:

    t = re.sub(r"^\s*```(?:html|md|markdown)?\s*", "", t, flags=re.I)  # CHANGED:
    t = re.sub(r"\s*```\s*$", "", t, flags=re.M)  # CHANGED:
    t = t.replace("```", "")  # CHANGED:
    t = t.replace("`", "")  # CHANGED:

    def _link_repl(m: re.Match) -> str:  # CHANGED:
        txt = (m.group(1) or "").strip() or "link"
        url = (m.group(2) or "").strip()
        href = _href_from_url_like(url)
        if not href:
            return html.escape(f"{txt} ({url})", quote=False)
        txt_esc = html.escape(txt, quote=False)
        href_esc = html.escape(href, quote=True)
        return f'<a href="{href_esc}" target="_blank" rel="nofollow noopener">{txt_esc}</a>'

    t = _MD_LINK_RE.sub(_link_repl, t)  # CHANGED:
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)  # CHANGED:
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", t)  # CHANGED:

    if re.search(r"^\s*#{1,3}\s+\S+", t, flags=re.M):  # CHANGED:
        out_lines: list[str] = []
        for line in t.splitlines():
            m = re.match(r"^\s*(#{1,3})\s+(.+?)\s*$", line)
            if m:
                level = len(m.group(1))
                text = (m.group(2) or "").strip()
                tag = "h3" if level >= 3 else "h2"  # CHANGED:
                out_lines.append(f"<{tag}>{html.escape(text, quote=False)}</{tag}>")
            else:
                out_lines.append(line)
        t = "\n".join(out_lines)

    t = _linkify_bare_urls_htmlish(t)  # CHANGED:

    if "<article" not in t.lower():  # CHANGED:
        t = f"<article class='ppa-preview'>\n{t}\n</article>"  # CHANGED:

    return t


def _build_title(subject: Optional[str], genre: Optional[str], tone: Optional[str]) -> str:
    parts = []
    if genre:
        parts.append(f"[{genre.strip()}]")
    if subject:
        parts.append(subject.strip())
    if tone:
        parts.append(f"— {tone.strip()}")
    return " ".join(parts) if parts else "Article — Neutral"


def _preview_json_schema() -> Dict[str, Any]:
    return {
        "name": "postpress_preview",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "html": {"type": "string", "minLength": 1, "maxLength": 100000},
                "summary": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "required": ["title", "html", "summary"],
        },
        "strict": True,
    }


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
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


def _validate_and_fill_contract(
    obj: Optional[Dict[str, Any]],
    payload: Dict[str, Any],
    provider_label: str,
) -> Dict[str, str]:
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
    if not out["summary"]:
        out["summary"] = "Generated preview."

    out["title"] = _demote_markdown_text(out["title"])  # CHANGED:
    out["summary"] = _demote_markdown_text(out["summary"])  # CHANGED:
    out["html"] = _sanitize_html_output(out["html"])  # CHANGED:

    if "<!-- provider:" not in out["html"]:
        out["html"] = out["html"].rstrip() + f"<!-- provider: {provider_label} -->"
    return out


# --------------------------------------------------------------------------------------
# Usage accounting (tokens)
# --------------------------------------------------------------------------------------

def _safe_int(v: Any) -> int:  # CHANGED:
    try:
        n = int(v)
        return n if n >= 0 else 0
    except Exception:
        return 0


def _extract_usage_openai(resp_json: Dict[str, Any]) -> Dict[str, int]:  # CHANGED:
    usage = resp_json.get("usage")
    if isinstance(usage, dict):
        pt = _safe_int(usage.get("prompt_tokens"))
        ct = _safe_int(usage.get("completion_tokens"))
        tt = _safe_int(usage.get("total_tokens") or (pt + ct))
        return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _extract_usage_anthropic(resp_json: Dict[str, Any]) -> Dict[str, int]:  # CHANGED:
    usage = resp_json.get("usage")
    if isinstance(usage, dict):
        inp = _safe_int(usage.get("input_tokens"))
        out = _safe_int(usage.get("output_tokens"))
        return {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": (inp + out)}
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _license_usage_field_name() -> Optional[str]:  # CHANGED:
    try:
        from postpress_ai.models.license import License
        field_names = {f.name for f in License._meta.get_fields() if hasattr(f, "name")}
    except Exception:
        return None

    ranked = [
        "monthly_tokens_used",
        "monthly_used_tokens",
        "tokens_used_this_period",
        "tokens_used_current_period",
        "tokens_used_month",
        "tokens_used_monthly",
        "monthly_usage_tokens",
        "monthly_used",
        "tokens_used",
        "token_used",
        "used_tokens",
    ]
    for c in ranked:
        if c in field_names:
            return c

    scored: list[tuple[int, str]] = []
    for name in field_names:
        n = name.lower()
        if "used" not in n:
            continue
        if ("token" not in n) and ("tokens" not in n):
            continue
        score = 0
        if "month" in n or "monthly" in n:
            score += 3
        if "period" in n:
            score += 2
        if "current" in n or "this" in n:
            score += 1
        score += 1
        scored.append((score, name))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]

    return None


# CHANGED: cached schema introspection to stay fast + avoid import-time coupling
_UE_FIELDS: Optional[set[str]] = None  # CHANGED:
_UE_REQUIRED_DEFAULTS: Optional[Dict[str, Any]] = None  # CHANGED:


def _usageevent_fields_and_required_defaults() -> tuple[set[str], Dict[str, Any]]:  # CHANGED:
    """
    Introspect UsageEvent schema safely.
    Returns:
      - fields: set of field names
      - required_defaults: defaults for non-null, non-blank fields that have no default
        (EXCEPT relational fields like ForeignKey, which must be set explicitly).
    """
    global _UE_FIELDS, _UE_REQUIRED_DEFAULTS  # CHANGED:
    if _UE_FIELDS is not None and _UE_REQUIRED_DEFAULTS is not None:
        return _UE_FIELDS, _UE_REQUIRED_DEFAULTS

    try:
        from postpress_ai.models.usage_event import UsageEvent  # local import
        fields: set[str] = set()
        required_defaults: Dict[str, Any] = {}

        for f in UsageEvent._meta.fields:
            name = getattr(f, "name", None)
            if not name:
                continue
            fields.add(name)

            if getattr(f, "primary_key", False):
                continue
            if getattr(f, "auto_created", False):
                continue
            if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
                continue
            if getattr(f, "null", False):
                continue
            if getattr(f, "blank", False):
                continue
            try:
                if f.has_default():
                    continue
            except Exception:
                pass

            if isinstance(f, (models.ForeignKey, models.OneToOneField)):  # CHANGED:
                continue

            if isinstance(f, (models.CharField, models.TextField)):
                required_defaults[name] = ""
            elif isinstance(
                f,
                (
                    models.IntegerField,
                    models.BigIntegerField,
                    models.PositiveIntegerField,
                    models.PositiveBigIntegerField,
                    models.SmallIntegerField,
                ),
            ):
                required_defaults[name] = 0
            elif isinstance(f, models.BooleanField):
                required_defaults[name] = False
            else:
                required_defaults[name] = ""

        _UE_FIELDS = fields
        _UE_REQUIRED_DEFAULTS = required_defaults
        return fields, required_defaults
    except Exception:
        _UE_FIELDS = set()
        _UE_REQUIRED_DEFAULTS = {}
        return _UE_FIELDS, _UE_REQUIRED_DEFAULTS


def _ensure_ctx_license_key() -> None:  # CHANGED:
    try:
        lk = _ctx_get_license_key()
        if lk:
            return
        site = _ctx_get_site_url()
        if not site:
            return
        derived = _derive_license_key_from_site(site)
        if derived:
            _ctx_set(license_key=derived, site_url=site)
            logger.info(
                "[PPA][preview_post][usage] derived_license_from_site site=%s license=%s",
                _normalize_site_url_for_lookup(site),
                _mask_key_for_log(derived),
            )
    except Exception:
        logger.exception("[PPA][preview_post][usage] ensure_ctx_failed")


def _write_usage_event(  # CHANGED:
    provider: str,
    usage: Dict[str, int],
    model_name: str = "",
    kind: str = "preview",
    endpoint: str = "preview_post.preview",
) -> bool:
    """
    Primary usage ledger write.
    Returns True if a UsageEvent row was created, else False (never raises).
    """
    try:
        _ensure_ctx_license_key()

        license_key = _ctx_get_license_key()
        if not license_key:
            return False

        total = _safe_int(usage.get("total_tokens"))
        if total <= 0:
            return False

        from postpress_ai.models.license import License
        lic_id = License.objects.filter(key=license_key).values_list("id", flat=True).first()
        if not lic_id:
            return False

        from postpress_ai.models.usage_event import UsageEvent
        fields, required_defaults = _usageevent_fields_and_required_defaults()

        data: Dict[str, Any] = {}
        data.update(required_defaults)

        if "license" in fields:
            data["license_id"] = lic_id
        elif "license_id" in fields:
            data["license_id"] = lic_id

        site = _ctx_get_site_url()
        norm_site = _normalize_site_url_for_lookup(site) if site else ""
        if norm_site:
            if "site_url" in fields:
                data["site_url"] = norm_site
            elif "site" in fields:
                data["site"] = norm_site
            elif "origin" in fields:
                data["origin"] = norm_site

        if "provider" in fields:
            data["provider"] = provider
        if model_name:
            if "model" in fields:
                data["model"] = model_name
            elif "model_name" in fields:
                data["model_name"] = model_name

        if "endpoint" in fields:
            data["endpoint"] = endpoint
        if "kind" in fields:
            data["kind"] = kind
        if "event_type" in fields:
            data["event_type"] = kind
        if "event" in fields:
            data["event"] = kind

        pt = _safe_int(usage.get("prompt_tokens"))
        ct = _safe_int(usage.get("completion_tokens"))

        if "prompt_tokens" in fields:
            data["prompt_tokens"] = pt
        if "completion_tokens" in fields:
            data["completion_tokens"] = ct
        if "total_tokens" in fields:
            data["total_tokens"] = total

        if "tokens_prompt" in fields:
            data["tokens_prompt"] = pt
        if "tokens_completion" in fields:
            data["tokens_completion"] = ct
        if "tokens_total" in fields:
            data["tokens_total"] = total
        if "tokens" in fields and "total_tokens" not in data and "tokens_total" not in data:
            data["tokens"] = total

        meta_obj = {
            "provider": provider,
            "model": model_name,
            "kind": kind,
            "endpoint": endpoint,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": total,
        }
        if "meta" in fields:
            data["meta"] = meta_obj
        elif "metadata" in fields:
            data["metadata"] = meta_obj
        elif "extra" in fields:
            data["extra"] = meta_obj

        UsageEvent.objects.create(**data)

        logger.info(
            "[PPA][preview_post][usage] usage_event_written provider=%s license=%s total=%s",
            provider,
            _mask_key_for_log(license_key),
            total,
        )
        return True
    except Exception:
        logger.exception("[PPA][preview_post][usage] usage_event_write_failed provider=%s", provider)
        return False


def _record_token_usage(provider: str, usage: Dict[str, int], model_name: str = "", kind: str = "preview") -> None:  # CHANGED:
    """
    Primary: UsageEvent ledger row.
    Fallback: legacy License-field increment.

    Best-effort only: never breaks generation.
    """
    try:
        _ensure_ctx_license_key()

        license_key = _ctx_get_license_key()
        total = _safe_int(usage.get("total_tokens"))
        if not license_key or total <= 0:
            return

        # CHANGED: ledger write first; if it works, do NOT also increment legacy field.
        if _write_usage_event(provider, usage, model_name=model_name, kind=kind):  # CHANGED:
            return

        # Legacy fallback (only if ledger write failed)
        field = _license_usage_field_name()
        if not field:
            logger.info(
                "[PPA][preview_post][usage] no_license_usage_field provider=%s license=%s total=%s",
                provider,
                _mask_key_for_log(license_key),
                total,
            )
            return

        from postpress_ai.models.license import License
        updated = License.objects.filter(key=license_key).update(
            **{field: Coalesce(F(field), 0) + total}
        )

        if updated != 1:
            logger.warning(
                "[PPA][preview_post][usage] license_update_unexpected updated=%s provider=%s license=%s",
                updated,
                provider,
                _mask_key_for_log(license_key),
            )
            return

        logger.info(
            "[PPA][preview_post][usage] recorded_legacy provider=%s license=%s field=%s total=%s",
            provider,
            _mask_key_for_log(license_key),
            field,
            total,
        )
    except Exception:
        logger.exception("[PPA][preview_post][usage] recording_failed provider=%s", provider)


# --------------------------------------------------------------------------------------
# Param enforcement (Genre/Tone/etc.)
# --------------------------------------------------------------------------------------
# (UNCHANGED BELOW — rest of your original file continues exactly as you pasted it,
#  with only the two call-sites updated to pass model/kind into _record_token_usage.)
# --------------------------------------------------------------------------------------

def _normalize_keywords(val: Any) -> str:  # CHANGED:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        parts = [_coerce_str(x) for x in val]
        parts = [p for p in parts if p]
        return ", ".join(parts)
    return _coerce_str(val)


def _normalize_word_count(payload: Dict[str, Any]) -> str:  # CHANGED:
    wc = payload.get("word_count")
    if wc is None or (isinstance(wc, str) and not wc.strip()):
        wc = payload.get("length")
    if wc is None:
        return ""
    try:
        n = int(str(wc).strip())
        if n > 0:
            return f"Target word count: ~{n} words."
    except Exception:
        pass
    s = _coerce_str(wc)
    if s:
        return f"Target length: {s}."
    return ""


def _style_rules_for_genre(genre_raw: str) -> str:  # CHANGED:
    g = (genre_raw or "").strip().lower()
    if not g or g == "auto":
        return (
            "STRUCTURE (Auto-Genre): Pick the best-fitting structure for the subject. "
            "Prefer clear headings, short paragraphs, and a practical flow."
        )

    aliases = {
        "how-to": "howto",
        "how_to": "howto",
        "tutorial": "tutorial",
        "guide": "tutorial",
        "list": "listicle",
        "checklist": "checklist",
        "news": "news",
        "review": "review",
        "case study": "case_study",
        "case-study": "case_study",
        "case_study": "case_study",
        "op-ed": "opinion",
        "opinion": "opinion",
    }
    g = aliases.get(g, g)

    rules: Dict[str, str] = {
        "tutorial": (
            "STRUCTURE (Tutorial): Teach step-by-step. Use clear sections with H2/H3, "
            "numbered steps where appropriate, and an end checklist. Include practical actions."
        ),
        "howto": (
            "STRUCTURE (How-to): Explain the process in order. Use H2/H3, steps, and concrete examples."
        ),
        "listicle": (
            "STRUCTURE (Listicle): Use a numbered list format (e.g., 7 items). Each item gets a heading "
            "and a short explanation. Finish with a quick recap."
        ),
        "checklist": (
            "STRUCTURE (Checklist): Lead with a short setup, then a checklist grouped by themes, "
            "then a short closing. Keep items scannable."
        ),
        "news": (
            "STRUCTURE (News): Lead with a short lede, then context, then key points, then what’s next. "
            "Avoid fiction; keep it factual and neutral."
        ),
        "review": (
            "STRUCTURE (Review): Use sections: Summary, Pros, Cons, Who it’s for, Verdict. "
            "If reviewing a process/tool, include practical takeaways."
        ),
        "case_study": (
            "STRUCTURE (Case Study): Use: Situation → Problem → Approach → Results → Lessons → Next steps. "
            "Use clear headings and measurable outcomes when possible."
        ),
        "opinion": (
            "STRUCTURE (Opinion): Make a clear thesis early, support it with 3–5 arguments, "
            "address a counterpoint, then close with a practical takeaway."
        ),
    }

    return rules.get(
        g,
        "STRUCTURE: Use clear headings, short paragraphs, and a logical progression from problem → solution → next steps.",
    )


def _style_rules_for_tone(tone_raw: str) -> str:  # CHANGED:
    t = (tone_raw or "").strip().lower()
    if not t or t == "auto":
        return (
            "VOICE (Auto-Tone): Choose a best-fit voice for the audience. "
            "Be clear, confident, and readable."
        )

    aliases = {
        "story": "storytelling",
        "story telling": "storytelling",
        "storytelling": "storytelling",
        "professional": "professional",
        "friendly": "friendly",
        "casual": "casual",
        "technical": "technical",
        "empathetic": "empathetic",
        "persuasive": "persuasive",
        "direct": "direct",
    }
    t = aliases.get(t, t)

    rules: Dict[str, str] = {
        "storytelling": (
            "VOICE (Storytelling): Open with a short scene (2–4 sentences) that creates stakes. "
            "Keep a light narrative thread through the piece (callbacks, momentum), while still being practical."
        ),
        "professional": (
            "VOICE (Professional): Crisp, neutral, and credible. Avoid hype. Favor clarity over flair."
        ),
        "friendly": (
            "VOICE (Friendly): Warm, helpful, human. Use plain language and supportive phrasing."
        ),
        "casual": (
            "VOICE (Casual): Conversational, relaxed, modern. Keep it tight and easy to read."
        ),
        "technical": (
            "VOICE (Technical): Precise and specific. Define terms briefly. Use exact steps and cautions."
        ),
        "empathetic": (
            "VOICE (Empathetic): Acknowledge stress/pain points. Be reassuring, calm, and practical."
        ),
        "persuasive": (
            "VOICE (Persuasive): Strong reasons, clear benefits, light urgency without fear-mongering. "
            "Use proof-like phrasing and clear calls-to-action."
        ),
        "direct": (
            "VOICE (Direct): No fluff. Short sentences. Clear actions. Strong but respectful tone."
        ),
    }

    return rules.get(t, "VOICE: Clear, neutral, and readable. Avoid filler and keep a steady pace.")


def _build_style_contract(payload: Dict[str, Any]) -> str:  # CHANGED:
    subject = _coerce_str(payload.get("subject") or payload.get("title"))
    genre = _coerce_str(payload.get("genre") or "")
    tone = _coerce_str(payload.get("tone") or "")
    audience = _coerce_str(payload.get("audience") or payload.get("target") or payload.get("target_audience"))
    word_count = _normalize_word_count(payload)
    keywords = _normalize_keywords(payload.get("keywords"))
    cta = _coerce_str(payload.get("cta") or payload.get("call_to_action"))

    brief = _demote_markdown_text(
        _coerce_str(
            payload.get("brief")
            or payload.get("instructions")
            or payload.get("content")
            or payload.get("text")
        )
    )

    lines = []
    lines.append("HARD CONSTRAINTS (must follow):")
    lines.append(f"- Subject: {subject or 'n/a'}")
    lines.append(f"- Genre: {genre or 'Auto'}")
    lines.append(f"- Tone: {tone or 'Auto'}")
    lines.append(f"- Audience: {audience or 'general readers'}")
    if word_count:
        lines.append(f"- {word_count}")
    if keywords:
        lines.append(f"- Keywords to naturally include where relevant: {keywords}")
    if cta:
        lines.append(f"- CTA: {cta}")
    if brief:
        lines.append(f"- Extra instructions: {brief}")

    lines.append("")
    lines.append(_style_rules_for_genre(genre))
    lines.append(_style_rules_for_tone(tone))

    lines.append("")
    lines.append(
        "HTML RULES: Output WordPress-ready HTML inside <article>. "
        "Use <h2>/<h3> for section headings. "
        "Do NOT include an <h1> that repeats the title. "
        "Keep paragraphs short and scannable."
    )

    lines.append(
        "MARKDOWN BAN: Output must contain ZERO Markdown syntax. "
        "Do NOT use [text](url) links, backticks, or markdown headings. "
        "If you include a link, use an HTML anchor like: <a href='https://example.com'>Example</a>."
    )

    lines.append("")
    lines.append("COMPLIANCE CHECK (do internally before output):")
    lines.append("- Did you follow the Genre structure rules?")
    lines.append("- Did you follow the Tone voice rules?")
    lines.append("- Did you avoid repeating the title as an H1 in the body HTML?")
    lines.append("- Did you ensure there is ZERO Markdown syntax anywhere in title/html/summary?")
    lines.append("- Are you returning ONLY JSON with title/html/summary?")

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Provider choice
# --------------------------------------------------------------------------------------

_rr_lock = threading.Lock()
_rr_next = 0


def _truthy_env(name: str) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _is_final_request(payload: Dict[str, Any]) -> bool:
    try:
        q = str(payload.get("quality") or payload.get("tier") or "").strip().lower()
    except Exception:
        q = ""
    mode = str(payload.get("mode") or "").strip().lower()
    if q in {"final", "publish", "high", "store"}:
        return True
    if mode == "publish":
        return True
    if _truthy_env("PPA_PREVIEW_FORCE_FINAL"):
        return True
    return False


def _detect_providers() -> Dict[str, bool]:
    have_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
    have_anthropic = bool(os.getenv("CLAUDE_API_KEY", "").strip())
    return {"openai": have_openai, "anthropic": have_anthropic}


def _choose_provider() -> Optional[str]:
    avail = _detect_providers()
    pref = (os.getenv("PPA_PREVIEW_PROVIDER") or "").strip().lower()
    strat = (os.getenv("PPA_PREVIEW_STRATEGY") or "").strip().lower()

    if pref in {"openai", "anthropic"}:
        return pref if avail.get(pref) else None

    both = avail.get("openai") and avail.get("anthropic")
    if both and (strat == "round_robin" or (pref in ("", "auto") and strat == "")):
        global _rr_next
        with _rr_lock:
            chosen = "openai" if (_rr_next % 2 == 0) else "anthropic"
            _rr_next += 1
        return chosen

    return "openai" if avail.get("openai") else ("anthropic" if avail.get("anthropic") else None)


# --------------------------------------------------------------------------------------
# Provider calls (OpenAI / Anthropic)
# --------------------------------------------------------------------------------------

def _build_user_prompt(payload: Dict[str, Any]) -> str:
    subject = _coerce_str(payload.get("subject") or payload.get("title"))
    genre = _coerce_str(payload.get("genre") or "Auto")
    tone = _coerce_str(payload.get("tone") or "Auto")
    audience = _coerce_str(payload.get("audience") or payload.get("target") or payload.get("target_audience"))

    keywords = _normalize_keywords(payload.get("keywords"))
    wc_directive = _normalize_word_count(payload)

    header_lines = [
        f"Subject: {subject or 'n/a'}",
        f"Genre: {genre}",
        f"Tone: {tone}",
        f"Audience: {audience or 'general readers'}",
    ]
    if keywords:
        header_lines.append(f"Keywords: {keywords}")
    if wc_directive:
        header_lines.append(wc_directive)

    contract = _build_style_contract(payload)

    parts = []
    parts.append("INPUT FIELDS:")
    parts.extend(header_lines)
    parts.append("")
    parts.append(contract)
    parts.append("")
    parts.append("OUTPUT FORMAT (mandatory):")
    parts.append("Return ONLY a JSON object with keys: title (string), html (string), summary (string).")
    parts.append("Do not wrap in markdown. Do not include commentary. Do not include extra keys.")
    parts.append("CRITICAL: html MUST be real HTML (not markdown). Links must be <a href='...'>.</a>")

    return "\n".join(parts)


def _openai_model(final: bool) -> str:
    if final:
        return (os.getenv("PPA_PREVIEW_FINAL_OPENAI_MODEL") or "").strip() or "gpt-4.1"
    return (os.getenv("PPA_PREVIEW_OPENAI_MODEL") or "").strip() or "gpt-4o-mini"


def _anthropic_model(final: bool) -> str:
    if final:
        return (os.getenv("PPA_PREVIEW_FINAL_ANTHROPIC_MODEL") or "").strip() or "claude-3-5-sonnet-20240620"
    return (os.getenv("PPA_PREVIEW_ANTHROPIC_MODEL") or "").strip() or "claude-sonnet-4-20250514"


def _generate_via_openai(payload: Dict[str, Any]) -> Dict[str, str]:
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
            {
                "role": "system",
                "content": (
                    "You are PostPress AI. You MUST follow the provided Genre/Tone/Audience/Length constraints. "
                    "Output ONLY strict JSON that matches the provided schema. No extra text. "
                    "IMPORTANT: The html field must be HTML, NEVER Markdown."
                ),
            },
            {"role": "user", "content": f"Build a blog post preview as JSON.\n{_build_user_prompt(payload)}"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": _preview_json_schema(),
        },
        "max_tokens": 1600,
    }

    try:
        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        usage = _extract_usage_openai(data)
        _record_token_usage("openai", usage, model_name=model, kind=("final" if final else "preview"))  # CHANGED:

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


def _generate_via_anthropic(payload: Dict[str, Any]) -> Dict[str, str]:
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
        "system": (
            "You are PostPress AI. You MUST follow the provided Genre/Tone/Audience/Length constraints. "
            "Output ONLY a JSON object with title/html/summary. No extra text. "
            "IMPORTANT: The html field must be HTML, NEVER Markdown."
        ),
        "messages": [
            {"role": "user", "content": f"Build a blog post preview as JSON.\n{_build_user_prompt(payload)}"},
        ],
    }

    try:
        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        usage = _extract_usage_anthropic(data)
        _record_token_usage("anthropic", usage, model_name=model, kind=("final" if final else "preview"))  # CHANGED:

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
# Loader & entry point
# --------------------------------------------------------------------------------------

def _load_service_generator() -> Optional[Callable[[Dict[str, Any]], Dict[str, str]]]:
    provider = _choose_provider()
    if provider == "openai":
        return _generate_via_openai
    if provider == "anthropic":
        return _generate_via_anthropic
    return None


def generate_preview(
    payload: Optional[Dict[str, Any]] = None,
    service_generator: Optional[Any] = None,
    request: Optional[Any] = None,
) -> Dict[str, str]:
    payload = payload or {}
    keys = sorted(list(payload.keys()))
    logger.info("[PPA][preview_post] keys=%s provider_env=%s", keys, os.getenv("PPA_PREVIEW_PROVIDER", ""))

    try:
        _ensure_ctx_license_key()
    except Exception:
        pass

    gen = service_generator if callable(service_generator) else _load_service_generator()

    if callable(gen):
        try:
            return gen(payload)
        except Exception as e:
            logger.warning("[PPA][preview_post] provider error=%s; using local fallback", e)

    subject = _coerce_str(payload.get("subject") or payload.get("title"))
    genre = _coerce_str(payload.get("genre"))
    tone = _coerce_str(payload.get("tone"))
    title = _build_title(subject, genre, tone)

    html_out = (
        "<!-- provider: local-fallback -->\n"
        "<article class='ppa-preview'>\n"
        f"  <header>\n"
        f"    <h2>{_sanitize_inline(title)}</h2>\n"
        f"    <p class='ppa-meta'><strong>Genre:</strong> { _sanitize_inline(genre) or '—' } | "
        f"<strong>Tone:</strong> { _sanitize_inline(tone) or '—' }</p>\n"
        f"  </header>\n"
        f"  <p>Preview not available; provider offline.</p>\n"
        f"</article>"
    ).strip()

    return {"title": title, "html": html_out, "summary": "Local fallback preview."}


# --------------------------------------------------------------------------------------
# Delegate view used by wrapper (views.preview calls this module)
# --------------------------------------------------------------------------------------

def preview(request: HttpRequest) -> JsonResponse | HttpResponse:
    """
    Delegate endpoint used by the public wrapper to generate content via providers.
    The outer wrapper performs CORS/auth (X-PPA-Key).
    """
    try:
        try:
            data = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            data = {}

        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}

        license_key = _coerce_str(
            data.get("license_key")
            or fields.get("license_key")
            or fields.get("ppa_license_key")
            or request.headers.get("X-PPA-License")
            or request.headers.get("X-PPA-License-Key")
            or request.META.get("HTTP_X_PPA_LICENSE")
            or request.META.get("HTTP_X_PPA_LICENSE_KEY")
        )
        site_url = _coerce_str(
            data.get("site_url")
            or fields.get("site_url")
            or fields.get("site")
            or request.headers.get("X-PPA-Site")
            or request.headers.get("X-PPA-Site-Url")
            or request.META.get("HTTP_X_PPA_SITE")
            or request.META.get("HTTP_X_PPA_SITE_URL")
            or request.headers.get("Origin")
            or request.META.get("HTTP_ORIGIN")
            or request.headers.get("Referer")
            or request.META.get("HTTP_REFERER")
        )
        _ctx_set(license_key=license_key, site_url=site_url)

        try:
            qd = getattr(request, "POST", None)
            if qd:
                for k, vals in qd.lists():
                    if k in ("action", "nonce"):
                        continue
                    if k.startswith("fields[") and k.endswith("]"):
                        kk = k[len("fields[") : -1]
                        if kk and kk not in fields and vals:
                            fields[kk] = str(vals[-1])
                    else:
                        if k not in fields and vals:
                            fields[k] = str(vals[-1])
        except Exception:
            pass

        if request.method == "POST" and getattr(request, "POST", None):
            import re
            skip = {"action", "nonce"}
            for k, v in request.POST.items():
                if k in skip:
                    continue
                m = re.match(r"^fields\[(?P<name>[^\]]+)\]$", k)
                if m:
                    name = m.group("name").strip()
                    if name and name not in skip:
                        fields[name] = v
                elif k not in fields:
                    fields[k] = v

        if not (isinstance(fields.get("title"), str) and fields.get("title").strip()):
            for alt in ("subject", "headline"):
                v = fields.get(alt)
                if isinstance(v, str) and v.strip():
                    fields["title"] = v
                    break

        license_key2 = _coerce_str(
            data.get("license_key")
            or fields.get("license_key")
            or fields.get("ppa_license_key")
            or license_key
        )
        site_url2 = _coerce_str(
            data.get("site_url")
            or fields.get("site_url")
            or fields.get("site")
            or site_url
            or request.headers.get("Origin")
            or request.META.get("HTTP_ORIGIN")
            or request.headers.get("Referer")
            or request.META.get("HTTP_REFERER")
        )

        if not license_key2 and site_url2:
            derived = _derive_license_key_from_site(site_url2)
            if derived:
                license_key2 = derived

        _ctx_set(license_key=license_key2, site_url=site_url2)

        logger.info("[PPA][preview_post][delegate] Processing fields: %s", list(fields.keys()))

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
    finally:
        _ctx_clear()
