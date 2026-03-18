from __future__ import annotations

import secrets
from typing import Any, Dict
from urllib.parse import urljoin

import requests
from django.conf import settings


def generate_site_token() -> str:
    return secrets.token_urlsafe(32)


def _timeout_seconds() -> int:
    try:
        return int(getattr(settings, "POSTPRESS_AI_REQUEST_TIMEOUT", 10))
    except Exception:
        return 10


def _backend_token() -> str:
    return str(
        getattr(settings, "PPA_SHARED_KEY", "")
        or getattr(settings, "POSTPRESS_AI_BACKEND_TOKEN", "")
        or ""
    ).strip()


def call_site_handshake(*, site_url: str, license_key: str, site_id: int, site_token: str) -> requests.Response:
    endpoint = urljoin(site_url.rstrip("/") + "/", "wp-json/postpress-ai/v1/site-handshake")

    backend_token = _backend_token()

    payload: Dict[str, Any] = {
        "license_key": license_key,
        "site_id": str(site_id),
        "site_token": site_token,
        "backend_token": backend_token,
    }

    headers = {
        "Content-Type": "application/json",
    }
    if backend_token:
        headers["x-postpress-ai-handshake"] = backend_token

    return requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=_timeout_seconds(),
    )

    headers = {
        "Content-Type": "application/json",
    }
    if backend_token:
        headers["x-postpress-ai-handshake"] = backend_token

    return requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=_timeout_seconds(),
    )


def call_remote_draft(*, target_site_url: str, target_site_token: str, post_payload: Dict[str, Any]) -> requests.Response:
    endpoint = urljoin(target_site_url.rstrip("/") + "/", "wp-json/postpress-ai/v1/remote-draft")

    headers = {
        "Authorization": f"Bearer {target_site_token}",
        "Content-Type": "application/json",
    }

    return requests.post(
        endpoint,
        headers=headers,
        json=post_payload,
        timeout=_timeout_seconds(),
    )
