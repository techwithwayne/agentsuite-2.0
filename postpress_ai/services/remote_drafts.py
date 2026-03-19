from __future__ import annotations

import secrets
import time
from typing import Any, Dict
from urllib.parse import urljoin

import requests
from django.conf import settings
from requests import Response
from requests.exceptions import RequestException


def generate_site_token() -> str:
    return secrets.token_urlsafe(32)


def _connect_timeout_seconds() -> float:
    try:
        return float(getattr(settings, "POSTPRESS_AI_CONNECT_TIMEOUT", 5))
    except Exception:
        return 5.0


def _read_timeout_seconds() -> float:
    try:
        return float(
            getattr(
                settings,
                "POSTPRESS_AI_REQUEST_TIMEOUT",
                getattr(settings, "POSTPRESS_AI_READ_TIMEOUT", 10),
            )
        )
    except Exception:
        return 10.0


def _request_timeout() -> tuple[float, float]:
    return (_connect_timeout_seconds(), _read_timeout_seconds())


def _max_attempts() -> int:
    try:
        value = int(getattr(settings, "POSTPRESS_AI_REMOTE_DRAFT_MAX_ATTEMPTS", 2))
        return value if value > 0 else 2
    except Exception:
        return 2


def _retry_delay_seconds() -> float:
    try:
        value = float(getattr(settings, "POSTPRESS_AI_REMOTE_DRAFT_RETRY_DELAY", 0.75))
        return value if value >= 0 else 0.75
    except Exception:
        return 0.75


def _backend_token() -> str:
    return str(
        getattr(settings, "PPA_SHARED_KEY", "")
        or getattr(settings, "POSTPRESS_AI_BACKEND_TOKEN", "")
        or ""
    ).strip()


def _user_agent() -> str:
    return "PostPressAI-Backend/remote-drafts"


def _is_retryable_response(resp: Response) -> bool:
    return resp.status_code in (408, 425, 429, 500, 502, 503, 504)


def _post_with_retry(*, endpoint: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Response:
    last_exc: Exception | None = None
    session = requests.Session()
    attempts = _max_attempts()

    for attempt in range(1, attempts + 1):
        try:
            resp = session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=_request_timeout(),
            )
        except RequestException as exc:
            last_exc = exc
            if attempt >= attempts:
                raise
            time.sleep(_retry_delay_seconds())
            continue

        if not _is_retryable_response(resp) or attempt >= attempts:
            return resp

        time.sleep(_retry_delay_seconds())

    if last_exc:
        raise last_exc

    raise RuntimeError("Remote draft request failed without a response.")


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
        "User-Agent": _user_agent(),
    }
    if backend_token:
        headers["x-postpress-ai-handshake"] = backend_token

    return _post_with_retry(
        endpoint=endpoint,
        headers=headers,
        payload=payload,
    )


def call_remote_draft(*, target_site_url: str, target_site_token: str, post_payload: Dict[str, Any]) -> requests.Response:
    endpoint = urljoin(target_site_url.rstrip("/") + "/", "wp-json/postpress-ai/v1/remote-draft")

    payload = dict(post_payload or {})
    payload.setdefault("remote_draft_token", target_site_token)
    payload.setdefault("postpress_ai_site_token", target_site_token)

    headers = {
        "Authorization": f"Bearer {target_site_token}",
        "x-postpress-ai-remote-draft": target_site_token,
        "x-ppa-remote-draft-token": target_site_token,
        "Content-Type": "application/json",
        "User-Agent": _user_agent(),
    }

    return _post_with_retry(
        endpoint=endpoint,
        headers=headers,
        payload=payload,
    )
