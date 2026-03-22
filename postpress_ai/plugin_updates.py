from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from django.conf import settings
from django.urls import reverse

log = logging.getLogger(__name__)


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return None
    value = value.strip()
    return value or None


def _empty_snapshot() -> Dict[str, Any]:
    return {
        "available": False,
        "latest_version": "",
        "download_url": None,
        "filename": "",
        "changelog": "",
        "released_at": None,
    }


def _build_download_url() -> Optional[str]:
    download_url = None
    base = _opt_str(getattr(settings, "DEPLOY_BASE_URL", None)) or _opt_str(os.environ.get("DEPLOY_BASE_URL"))

    try:
        download_path = reverse("postpress_ai:ppa-plugin-download")
    except Exception as exc:
        log.warning("PPA plugin release reverse failed for ppa-plugin-download: %s", exc)
        return None

    if not download_path:
        return None

    download_path = str(download_path).strip()
    if download_path.startswith("http://") or download_path.startswith("https://"):
        download_url = download_path
    elif base:
        if not download_path.startswith("/"):
            download_path = "/" + download_path
        download_url = base.rstrip("/") + download_path
    else:
        download_url = download_path

    return _opt_str(download_url)


def _release_file_exists(rel: Any) -> bool:
    zip_file = getattr(rel, "zip_file", None)
    if not zip_file:
        return False

    file_name = _opt_str(getattr(zip_file, "name", None))
    if not file_name:
        return False

    try:
        return bool(zip_file.storage.exists(file_name))
    except Exception as exc:
        log.warning("PPA plugin release storage.exists failed for %r: %s", file_name, exc)
        return False


def plugin_update_snapshot() -> Dict[str, Any]:
    try:
        from postpress_ai.models.plugin_release import PluginRelease
    except Exception:
        return _empty_snapshot()

    rel = (
        PluginRelease.objects.filter(product_slug="postpress-ai", is_active=True)
        .order_by("-released_at", "-id")
        .first()
    )

    if not rel:
        return _empty_snapshot()

    filename = _opt_str(getattr(rel, "filename", None))
    if not filename:
        try:
            filename = os.path.basename(rel.zip_file.name or "")
        except Exception:
            filename = ""

    file_exists = _release_file_exists(rel)
    download_url = _build_download_url() if file_exists else None
    available = bool(file_exists and download_url)

    if not file_exists:
        log.warning(
            "PPA plugin release inactive-for-delivery: active row exists but file is missing. "
            "release_id=%s version=%s zip_name=%r",
            getattr(rel, "id", None),
            getattr(rel, "version", None),
            getattr(getattr(rel, "zip_file", None), "name", None),
        )
    elif not download_url:
        log.warning(
            "PPA plugin release inactive-for-delivery: active file exists but download URL could not be built. "
            "release_id=%s version=%s",
            getattr(rel, "id", None),
            getattr(rel, "version", None),
        )

    return {
        "available": available,
        "latest_version": _opt_str(getattr(rel, "version", None)) or "",
        "download_url": download_url,
        "filename": filename or "",
        "changelog": getattr(rel, "changelog", "") or "",
        "released_at": getattr(rel, "released_at", None),
    }
