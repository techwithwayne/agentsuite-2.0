"""
settings.py  tiny env-backed settings for agentsuite-2.0

This file is intentionally dependency-light (stdlib only).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "", required: bool = False) -> str:
    v = os.getenv(name, default)
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def as_bool(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "on")


@dataclass(frozen=True)
class Settings:
    # Auth between WP widget and this service
    PPA_WP_SHARED_SECRET: str = _env("PPA_WP_SHARED_SECRET", "", required=False)

    # UX links
    PPA_PLUGIN_DOWNLOAD_URL: str = _env("PPA_PLUGIN_DOWNLOAD_URL", "https://postpressai.com/download")

    # Support routing
    SUPPORT_EMAIL: str = _env("SUPPORT_EMAIL", "support@postpressai.com")

    # Optional LLM usage
    OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-4.1-mini")

    # Behavior flags
    REQUIRE_SHARED_SECRET: bool = as_bool(_env("REQUIRE_SHARED_SECRET", "1"))


SETTINGS = Settings()
