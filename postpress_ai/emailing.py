"""
postpress_ai.emailing

Email helpers for PostPress AI fulfillment (Django authoritative).

Purpose (Stripe Fulfillment phase):
- Send the purchaser their PostPress AI license key email after payment success.

LOCKED INTENT
- Django sends emails (server-side).
- WordPress never sends license emails.
- Keep this module dependency-light so it can be reused by webhook + admin tools.

ENV/SETTINGS
- Uses Django email backend config (EMAIL_HOST, EMAIL_HOST_USER, etc.)
- Uses DEFAULT_FROM_EMAIL (recommended)
- Optional: PPA_SUPPORT_EMAIL / PPA_PRODUCT_NAME via env vars for simple branding

========= CHANGE LOG =========
2025-12-26 • ADD: send_license_key_email() using EmailMultiAlternatives (text + HTML).  # CHANGED:
"""

from __future__ import annotations

import os
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _from_email() -> str:
    # Prefer DEFAULT_FROM_EMAIL; fall back to SERVER_EMAIL; last resort is a safe placeholder.  # CHANGED:
    return (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")  # CHANGED:
        or getattr(settings, "SERVER_EMAIL", "")  # CHANGED:
        or "no-reply@localhost"  # CHANGED:
    )


def _support_email() -> str:
    # Optional support contact (kept simple + overridable).  # CHANGED:
    return _env("PPA_SUPPORT_EMAIL", "")


def _product_name() -> str:
    return _env("PPA_PRODUCT_NAME", "PostPress AI")


def send_license_key_email(  # CHANGED:
    *,
    to_email: str,
    license_key: str,
    purchaser_name: Optional[str] = None,
    product_tier: Optional[str] = None,
) -> None:
    """
    Send the purchaser their license key.

    NOTE:
    - This function raises on failure (so webhook can 500 and Stripe retries during build).
    - Later we can soften this (queue, retry, mark status) once DB persistence is complete.
    """
    if not (to_email or "").strip():
        raise ValueError("to_email is required")
    if not (license_key or "").strip():
        raise ValueError("license_key is required")

    name = (purchaser_name or "").strip()
    tier = (product_tier or "").strip()
    product = _product_name()

    subject_bits = [product, "Your License Key"]
    if tier:
        subject_bits.insert(1, f"({tier})")
    subject = " — ".join(subject_bits)

    greeting = f"Hey {name}," if name else "Hey there,"
    support = _support_email()

    # Plain text (deliverability-first).  # CHANGED:
    text_lines = [
        greeting,
        "",
        "Your license key is ready:",
        "",
        f"{license_key}",
        "",
        "Keep this key somewhere safe — you’ll use it to activate PostPress AI.",
    ]
    if support:
        text_lines += [
            "",
            f"Need help? Reply to this email or contact: {support}",
        ]
    text_lines += [
        "",
        "— PostPress AI",
    ]
    text_body = "\n".join(text_lines)

    # Simple HTML (no fancy templates yet; we can upgrade once fulfillment is stable).  # CHANGED:
    html_body = f"""
<!doctype html>
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.5;">
    <p>{greeting}</p>

    <p>Your license key is ready:</p>

    <p style="font-size: 18px; font-weight: 700; letter-spacing: 1px;">
      {license_key}
    </p>

    <p>Keep this key somewhere safe — you’ll use it to activate PostPress AI.</p>

    {"<p>Need help? Reply to this email or contact: " + support + "</p>" if support else ""}

    <p>— PostPress AI</p>
  </body>
</html>
""".strip()

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=_from_email(),
        to=[to_email.strip()],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)  # CHANGED:
