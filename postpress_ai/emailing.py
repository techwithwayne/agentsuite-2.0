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

2025-12-26  # CHANGED:
- ADD: send_license_key_email() using EmailMultiAlternatives (text + HTML).  # CHANGED:

2026-01-10  # CHANGED:
- FIX: Inline logo loads from app static path (not remote URL).             # CHANGED:
- ADD: Subject support + warm “from Wayne” customer-love copy.             # CHANGED:
- KEEP: Backward compatibility with existing webhook call signature.       # CHANGED:
"""

from __future__ import annotations

import logging
import os
from email.mime.image import MIMEImage
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

log = logging.getLogger("webdoctor")

DEFAULT_SUBJECT = "Welcome to PostPress AI — here’s your key"  # CHANGED:
DEFAULT_PRODUCT_TIER = "Tyler"  # CHANGED:

# CHANGED: Put your logo here inside the app.
# You should place a PNG at:
#   postpress_ai/static/postpress_ai/email/postpress-ai-logo.png
#
# Then Django staticfiles can find it reliably in dev and prod.
LOGO_STATIC_RELATIVE_PATH = "postpress_ai/email/postpress-ai-logo.png"  # CHANGED:


def _safe(s: Optional[str]) -> str:  # CHANGED:
    return (s or "").strip()


def _first_name_from_full(full_name: str) -> str:  # CHANGED:
    full_name = _safe(full_name)
    if not full_name:
        return ""
    return full_name.split()[0]


def _find_logo_file_path() -> Optional[str]:  # CHANGED:
    """
    Locate the logo file on disk via Django staticfiles finders if available.
    Falls back to a relative filesystem check for safety.

    Returns:
        Absolute filepath or None.
    """
    # 1) Preferred: django.contrib.staticfiles.finders.find
    try:  # CHANGED:
        from django.contrib.staticfiles import finders  # type: ignore  # CHANGED:

        p = finders.find(LOGO_STATIC_RELATIVE_PATH)  # CHANGED:
        if p and os.path.exists(p):  # CHANGED:
            return p  # CHANGED:
    except Exception:
        pass  # CHANGED:

    # 2) Fallback: try to find it relative to this file (works if you store it alongside repo)
    try:  # CHANGED:
        here = os.path.dirname(os.path.abspath(__file__))  # CHANGED:
        candidate = os.path.join(here, "static", *LOGO_STATIC_RELATIVE_PATH.split("/"))  # CHANGED:
        if os.path.exists(candidate):  # CHANGED:
            return candidate  # CHANGED:
    except Exception:
        pass  # CHANGED:

    return None  # CHANGED:


def _attach_inline_logo(msg: EmailMultiAlternatives, content_id: str = "ppa_logo") -> bool:  # CHANGED:
    """
    Attach an inline logo image (CID) if present.
    Returns True if attached.
    """
    path = _find_logo_file_path()  # CHANGED:
    if not path:
        log.warning("PPA email: logo not found at static path=%s (email will send without logo)", LOGO_STATIC_RELATIVE_PATH)
        return False  # CHANGED:

    try:
        with open(path, "rb") as f:
            img = MIMEImage(f.read())  # CHANGED:
        img.add_header("Content-ID", f"<{content_id}>")  # CHANGED:
        img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))  # CHANGED:
        msg.attach(img)  # CHANGED:
        return True  # CHANGED:
    except Exception as e:
        log.exception("PPA email: failed attaching inline logo: %s", str(e))
        return False  # CHANGED:


def send_license_key_email(  # CHANGED:
    *,
    to_email: str,
    license_key: str,
    purchaser_name: Optional[str] = None,
    product_tier: str = DEFAULT_PRODUCT_TIER,
    subject: str = DEFAULT_SUBJECT,  # CHANGED:
) -> None:
    """
    Send the PostPress AI license delivery email (text + HTML) with inline logo.

    Backward-compatible with existing webhook call signature:
      send_license_key_email(to_email=..., license_key=..., purchaser_name=..., product_tier=...)

    Raises on failure (so webhook can 500 and Stripe retries while wiring).
    """
    to_email = _safe(to_email).lower()  # CHANGED:
    license_key = _safe(license_key)  # CHANGED:
    purchaser_name = _safe(purchaser_name)  # CHANGED:
    product_tier = _safe(product_tier) or DEFAULT_PRODUCT_TIER  # CHANGED:
    subject = _safe(subject) or DEFAULT_SUBJECT  # CHANGED:

    if not to_email:
        raise ValueError("send_license_key_email: missing to_email")  # CHANGED:
    if not license_key:
        raise ValueError("send_license_key_email: missing license_key")  # CHANGED:

    first_name = _first_name_from_full(purchaser_name)  # CHANGED:
    hello = f"Hey {first_name}," if first_name else "Hey there,"  # CHANGED:

    # ---- Plain text (deliverability + accessibility) ----
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

    # ---- HTML (brand) ----
    # NOTE: Inline image uses CID ppa_logo. It will gracefully no-op if missing.
    html = f"""
<div style="background:#121212;padding:24px;font-family:Arial,sans-serif;">
  <div style="max-width:680px;margin:0 auto;background:#0f0f0f;border:1px solid #2a2a2a;border-radius:12px;overflow:hidden;">
    <div style="padding:16px 18px;border-bottom:1px solid #2a2a2a;display:flex;align-items:center;gap:12px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <img src="cid:ppa_logo" alt="PostPress AI" style="height:38px;display:block;" />
      </div>
    </div>

    <div style="padding:18px;color:#f2f2f2;line-height:1.55;">
      <h2 style="margin:0 0 10px 0;font-size:20px;font-weight:700;">Welcome to PostPress AI — here’s your key</h2>

      <p style="margin:0 0 14px 0;color:#e6e6e6;">
        {hello}<br/>
        You’re officially in. And since you’re here early… seriously: thank you.
        I built PostPress AI to make publishing inside WordPress feel smooth again — no extra tabs, no messy workflow.
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
          If anything doesn’t look right, just reply to this email.
          You won’t get routed through a maze — it’s me and my team, and we’ll get you unstuck.
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
        subject=subject,  # CHANGED:
        body=text,
        to=[to_email],
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or None,
    )  # CHANGED:
    msg.attach_alternative(html, "text/html")

    # Attach inline logo (doesn't break email if missing)
    _attach_inline_logo(msg, content_id="ppa_logo")  # CHANGED:

    # Send (raises on failure)
    sent_count = msg.send()  # CHANGED:
    if not sent_count:
        raise RuntimeError("Email backend returned 0 (not sent).")  # CHANGED:
