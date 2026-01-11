# /home/techwithwayne/agentsuite/postpress_ai/emailing.py

"""
PostPress AI — Emailing utilities
Path: postpress_ai/emailing.py

Purpose:
- Transactional email delivery (SendGrid via django-anymail backend).
- Branded license delivery email:
  Subject: "Welcome to PostPress AI — here’s your key"
- Inline logo served from within this Django app (no external URL dependency).
- Safe-by-default: if logo file missing, email still sends (just without image).

LOCKED INTENT
- Keep dependency-light and reusable by webhook + admin tools.
- Do NOT change contracts outside this module unless explicitly required.

======== CHANGE LOG ========
2025-12-26
- Keep this module dependency-light so it can be reused by webhook + admin tools.

2025-12-26
- ADD: send_license_key_email() using EmailMultiAlternatives (text + HTML).

2026-01-10  # CHANGED:
- FIX: Eliminate circular import risks: NO imports from postpress_ai.views.* or models.          # CHANGED:
- ADD: Support optional `headers` kwarg for Message-ID idempotency (webhook compatibility).    # CHANGED:
- FIX: Inline logo loads from app static path AND via staticfiles finders when available.      # CHANGED:
- KEEP: Subject must be exact: “Welcome to PostPress AI — here’s your key”.                    # CHANGED:

2026-01-11  # CHANGED:
- FIX: Accept webhook-friendly alias kwargs (name/tier/max_sites) without changing callers.    # CHANGED:
- KEEP: Subject locked EXACT (force DEFAULT_SUBJECT for license emails).                       # CHANGED:
"""

from __future__ import annotations

import logging
import os
from email.mime.image import MIMEImage
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

log = logging.getLogger("webdoctor")

DEFAULT_SUBJECT = "Welcome to PostPress AI — here’s your key"
DEFAULT_PRODUCT_TIER = "Tyler"

# Static-relative path (Django staticfiles convention)
LOGO_STATIC_RELATIVE_PATH = "postpress_ai/email/postpress-ai-logo.png"

# Absolute repo path fallback (works in dev + prod when repo present)
LOGO_ABS_FALLBACK_PATH = (
    Path(__file__).resolve().parent
    / "static"
    / "postpress_ai"
    / "email"
    / "postpress-ai-logo.png"
)


def _safe(s: Optional[str]) -> str:
    return (s or "").strip()


def _first_name_from_full(full_name: str) -> str:
    full_name = _safe(full_name)
    if not full_name:
        return ""
    return full_name.split()[0]


def _find_logo_file_path() -> Optional[str]:
    """
    Locate the logo file on disk.

    Priority:
    1) django.contrib.staticfiles.finders.find (if available)
    2) absolute fallback path inside this app repo
    3) None (email still sends without logo)
    """
    # 1) Preferred: django staticfiles finder (works after collectstatic too)
    try:
        from django.contrib.staticfiles import finders  # type: ignore

        p = finders.find(LOGO_STATIC_RELATIVE_PATH)
        if p and os.path.exists(p):
            return str(p)
    except Exception:
        pass

    # 2) Fallback: repo path next to this module
    try:
        if LOGO_ABS_FALLBACK_PATH.exists():
            return str(LOGO_ABS_FALLBACK_PATH)
    except Exception:
        pass

    return None


def _attach_inline_logo(msg: EmailMultiAlternatives, content_id: str = "ppa_logo") -> bool:
    """
    Attach inline PNG logo as CID so HTML can reference: <img src="cid:ppa_logo" ...>
    Returns True if attached.
    """
    path = _find_logo_file_path()
    if not path:
        log.warning(
            "PPA email: logo not found (email will send without image). expected=%s",
            LOGO_STATIC_RELATIVE_PATH,
        )
        return False

    try:
        with open(path, "rb") as f:
            img = MIMEImage(f.read(), _subtype="png")
        img.add_header("Content-ID", f"<{content_id}>")
        img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
        msg.attach(img)
        return True
    except Exception as e:
        log.exception("PPA email: failed attaching inline logo: %s", str(e))
        return False


def send_license_key_email(
    *,
    to_email: str,
    license_key: str,
    purchaser_name: Optional[str] = None,
    product_tier: str = DEFAULT_PRODUCT_TIER,
    subject: str = DEFAULT_SUBJECT,
    headers: Optional[Dict[str, Any]] = None,  # CHANGED:
    # --- Back-compat aliases for webhook callers ---                                   # CHANGED:
    name: Optional[str] = None,  # CHANGED:
    tier: Optional[str] = None,  # CHANGED:
    max_sites: Optional[int] = None,  # CHANGED: accepted (unused in email copy)
) -> None:
    """
    Send the PostPress AI license delivery email (text + HTML) with inline logo.

    Backward-compatible with webhook-friendly signature:
      send_license_key_email(to_email=..., license_key=..., name=..., tier=..., max_sites=...)

    Also accepts:
      headers={...}  (used by webhook for Message-ID idempotency)

    Raises on failure so webhook can 500 and Stripe retries (idempotent EmailLog prevents spam).
    """
    to_email = _safe(to_email).lower()
    license_key = _safe(license_key)

    # Alias resolution (webhook compatibility)                                           # CHANGED:
    if not purchaser_name and name:  # CHANGED:
        purchaser_name = name  # CHANGED:
    if (product_tier == DEFAULT_PRODUCT_TIER) and tier:  # CHANGED:
        product_tier = tier  # CHANGED:
    purchaser_name = _safe(purchaser_name)  # CHANGED:
    product_tier = _safe(product_tier) or DEFAULT_PRODUCT_TIER  # CHANGED:

    # Subject is LOCKED EXACT for license delivery.                                      # CHANGED:
    subject = DEFAULT_SUBJECT  # CHANGED:

    if not to_email:
        raise ValueError("send_license_key_email: missing to_email")
    if not license_key:
        raise ValueError("send_license_key_email: missing license_key")

    first_name = _first_name_from_full(purchaser_name)
    hello = f"Hey {first_name}," if first_name else "Hey there,"

    # Plain text
    text = f"""{hello}

Welcome to PostPress AI. I’m genuinely grateful you’re here — especially as an Early Bird.

Here’s your license key:
{license_key}

Quick start:
1) Install the PostPress AI plugin in WordPress
2) Go to PostPress AI → Settings → paste your key → Activate
3) Go to the Composer:
   - Click “Generate Preview”
   - Click “Save Draft (Store)”
4) Open the draft link and confirm it’s in WordPress

If anything feels weird or confusing, reply to this email. I read these.
— Wayne Hatter
Support: support@postpressai.com
"""

    # HTML (CID image: ppa_logo)
    html = f"""
<div style="background:#121212;padding:24px;font-family:Arial,sans-serif;">
  <div style="max-width:680px;margin:0 auto;background:#0f0f0f;border:1px solid #2a2a2a;border-radius:12px;overflow:hidden;">
    <div style="padding:16px 18px;border-bottom:1px solid #2a2a2a;display:flex;align-items:center;gap:12px;">
      <img src="cid:ppa_logo" alt="PostPress AI" style="height:38px;display:block;" />
    </div>

    <div style="padding:18px;color:#f2f2f2;line-height:1.55;">
      <h2 style="margin:0 0 10px 0;font-size:20px;font-weight:700;">Welcome to PostPress AI — here’s your key</h2>

      <p style="margin:0 0 14px 0;color:#e6e6e6;">
        {hello}<br/>
        You’re officially in. And since you’re here early… seriously: thank you.
      </p>

      <div style="margin-top:12px;padding:14px 14px;border:1px solid #ff6c00;border-radius:10px;background:rgba(255,108,0,0.06);">
        <div style="opacity:.85;font-size:12px;margin-bottom:6px;letter-spacing:.2px;">Your License Key</div>
        <div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:18px;word-break:break-all;">
          {license_key}
        </div>
        <div style="margin-top:10px;color:#cfcfcf;font-size:12px;opacity:.9;">
          Plan: <span style="color:#ffffff;">{product_tier}</span>
        </div>
      </div>

      <div style="margin-top:16px;padding:14px;border:1px solid #2a2a2a;border-radius:10px;">
        <div style="font-weight:700;margin-bottom:8px;">Quick start (2 minutes)</div>
        <ol style="margin:0;padding-left:18px;color:#eaeaea;">
          <li style="margin:0 0 6px 0;">Install the PostPress AI plugin in WordPress</li>
          <li style="margin:0 0 6px 0;">Go to <b>PostPress AI → Settings</b> → paste your key → <b>Activate</b></li>
          <li style="margin:0 0 6px 0;">Open the Composer and click <b>Generate Preview</b></li>
          <li style="margin:0 0 6px 0;">Click <b>Save Draft (Store)</b>, then open the draft link</li>
        </ol>
      </div>
      <div style="margin-top:16px;padding:14px;border:1px solid #2a2a2a;border-radius:10px;">
        <div style="font-weight:700;margin-bottom:8px;">Need help?</div>
        <p style="margin:0;color:#e6e6e6;">
          Reply to this email and we’ll get you unstuck.
        </p>
        <p style="margin:10px 0 0 0;color:#bdbdbd;font-size:12px;">
          Support: <a href="mailto:support@postpressai.com" style="color:#ff6c00;text-decoration:none;">support@postpressai.com</a>
        </p>
      </div>
      <p style="margin:18px 0 0 0;color:#bdbdbd;font-size:12px;">
        — Wayne Hatter, PostPress AI
      </p>
    </div>
  </div>
</div>
"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        to=[to_email],
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or None,
        headers=headers or None,
    )
    msg.attach_alternative(html, "text/html")
    _attach_inline_logo(msg, content_id="ppa_logo")
    sent_count = msg.send()
    if not sent_count:
        raise RuntimeError("Email backend returned 0 (not sent).")
