"""
postpress_ai.email_config

Env-driven email configuration for PostPress AI (transactional email).

GOAL
- NO django-anymail dependency.
- Use Django's built-in email backends:
  - SMTP (recommended for real delivery)
  - Console (safe fallback)

ENV
- PPA_EMAIL_PROVIDER: "auto" | "smtp" | "console"   (default: auto)
- DEFAULT_FROM_EMAIL: default sender

SMTP (if provider=auto or smtp)
- EMAIL_HOST / SMTP_HOST
- EMAIL_PORT
- EMAIL_HOST_USER / SMTP_USER
- EMAIL_HOST_PASSWORD / SMTP_PASSWORD
- EMAIL_USE_TLS
- EMAIL_USE_SSL

If SMTP is not configured, provider=auto falls back to console backend.
"""

from __future__ import annotations

import os
from typing import Dict


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _bool_env(name: str, default: str = "0") -> bool:
    v = _env(name, default).lower()
    return v in ("1", "true", "yes", "on")


def _int_env(name: str, default: str) -> int:
    try:
        return int(_env(name, default) or default)
    except Exception:
        return int(default)


def _smtp_is_configured() -> bool:
    return bool(_env("EMAIL_HOST") or _env("SMTP_HOST"))


def get_email_settings() -> Dict[str, object]:
    provider = _env("PPA_EMAIL_PROVIDER", "auto").lower()
    if provider not in ("auto", "smtp", "console"):
        provider = "auto"

    base: Dict[str, object] = {
        "DEFAULT_FROM_EMAIL": _env("DEFAULT_FROM_EMAIL", "no-reply@localhost"),
    }

    # Console backend (always safe)
    if provider == "console":
        base.update({"EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"})
        return base

    # SMTP backend (recommended)
    if provider == "smtp" or (provider == "auto" and _smtp_is_configured()):
        base.update(
            {
                "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                "EMAIL_HOST": _env("EMAIL_HOST") or _env("SMTP_HOST", "localhost"),
                "EMAIL_PORT": _int_env("EMAIL_PORT", "587"),
                "EMAIL_HOST_USER": _env("EMAIL_HOST_USER") or _env("SMTP_USER", ""),
                "EMAIL_HOST_PASSWORD": _env("EMAIL_HOST_PASSWORD") or _env("SMTP_PASSWORD", ""),
                "EMAIL_USE_TLS": _bool_env("EMAIL_USE_TLS", "1"),
                "EMAIL_USE_SSL": _bool_env("EMAIL_USE_SSL", "0"),
            }
        )
        return base

    # Auto fallback  console if SMTP isn't configured
    base.update({"EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"})
    return base
