"""
postpress_ai.email_config

Centralized, env-driven email configuration for PostPress AI (transactional email).
This exists so we can support multiple providers cleanly without rewriting fulfillment logic.

WHY THIS FILE EXISTS
- We already send transactional emails (license keys).
- Transactional email should NOT depend on Mailchimp marketing campaigns.
- Anymail is already in play in your stack (per the AnymailInvalidAddress error), so we standardize it.

LOCKED INTENT
- Django sends transactional emails (license keys).
- Provider choice is infra-only (env vars), not business logic.

SUPPORTED PROVIDERS (set PPA_EMAIL_PROVIDER)
- postmark   (recommended: simplest + great deliverability)
- mailgun
- sendgrid
- ses
- mandrill   (Mailchimp Transactional)
- smtp       (fallback / basic)

ENV VARS (common)
- PPA_EMAIL_PROVIDER            (default: "postmark")
- DEFAULT_FROM_EMAIL            (recommended)
- PPA_SUPPORT_EMAIL             (optional; used in email body)
- PPA_PRODUCT_NAME              (optional; used in email body)

Provider-specific ENV (examples)
POSTMARK
- POSTMARK_SERVER_TOKEN

MAILGUN
- MAILGUN_API_KEY
- MAILGUN_SENDER_DOMAIN

SENDGRID
- SENDGRID_API_KEY

SES
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_REGION

MANDRILL (Mailchimp Transactional)
- MANDRILL_API_KEY

SMTP
- EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS/SSL

========= CHANGE LOG =========
2025-12-26 • ADD: Env-driven email provider config helper for Anymail/SMPP.  # CHANGED:
"""

from __future__ import annotations

import os
from typing import Dict


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _bool_env(name: str, default: str = "0") -> bool:
    v = _env(name, default).lower()
    return v in ("1", "true", "yes", "on")


def get_email_settings() -> Dict[str, object]:  # CHANGED:
    """
    Returns a dict of Django settings to merge into your settings module.

    Usage (next file step in your settings.py):
        from postpress_ai.email_config import get_email_settings
        globals().update(get_email_settings())
    """
    provider = _env("PPA_EMAIL_PROVIDER", "postmark").lower()

    # Always provide these sane defaults; you can override via env.  # CHANGED:
    base: Dict[str, object] = {
        "DEFAULT_FROM_EMAIL": _env("DEFAULT_FROM_EMAIL", "no-reply@localhost"),
        # Optional: keep a predictable subject prefix if you want later.
        # "EMAIL_SUBJECT_PREFIX": _env("EMAIL_SUBJECT_PREFIX", ""),
    }

    # --- Provider: Postmark (recommended) ---
    if provider == "postmark":
        base.update(
            {
                "EMAIL_BACKEND": "anymail.backends.postmark.EmailBackend",
                "ANYMAIL": {
                    "POSTMARK_SERVER_TOKEN": _env("POSTMARK_SERVER_TOKEN"),
                },
            }
        )
        return base

    # --- Provider: Mailgun ---
    if provider == "mailgun":
        base.update(
            {
                "EMAIL_BACKEND": "anymail.backends.mailgun.EmailBackend",
                "ANYMAIL": {
                    "MAILGUN_API_KEY": _env("MAILGUN_API_KEY"),
                    "MAILGUN_SENDER_DOMAIN": _env("MAILGUN_SENDER_DOMAIN"),
                },
            }
        )
        return base

    # --- Provider: SendGrid ---
    if provider == "sendgrid":
        base.update(
            {
                "EMAIL_BACKEND": "anymail.backends.sendgrid.EmailBackend",
                "ANYMAIL": {
                    "SENDGRID_API_KEY": _env("SENDGRID_API_KEY"),
                },
            }
        )
        return base

    # --- Provider: Amazon SES ---
    if provider == "ses":
        # Anymail SES backend uses boto3 under the hood.
        base.update(
            {
                "EMAIL_BACKEND": "anymail.backends.amazon_ses.EmailBackend",
                "ANYMAIL": {
                    "AMAZON_SES_CLIENT_PARAMS": {
                        "region_name": _env("AWS_REGION", "us-east-1"),
                    }
                },
            }
        )
        return base

    # --- Provider: Mandrill (Mailchimp Transactional) ---
    if provider == "mandrill":
        base.update(
            {
                "EMAIL_BACKEND": "anymail.backends.mandrill.EmailBackend",
                "ANYMAIL": {
                    "MANDRILL_API_KEY": _env("MANDRILL_API_KEY"),
                },
            }
        )
        return base

    # --- Provider: SMTP fallback ---
    # Good for quick testing; not my favorite for production deliverability unless you know the host.
    base.update(
        {
            "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "EMAIL_HOST": _env("EMAIL_HOST", "localhost"),
            "EMAIL_PORT": int(_env("EMAIL_PORT", "25") or "25"),
            "EMAIL_HOST_USER": _env("EMAIL_HOST_USER", ""),
            "EMAIL_HOST_PASSWORD": _env("EMAIL_HOST_PASSWORD", ""),
            "EMAIL_USE_TLS": _bool_env("EMAIL_USE_TLS", "0"),
            "EMAIL_USE_SSL": _bool_env("EMAIL_USE_SSL", "0"),
        }
    )
    return base
