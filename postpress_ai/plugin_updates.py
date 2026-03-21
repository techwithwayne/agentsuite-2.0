from __future__ import annotations

import os
from typing import Any, Dict, Optional

from django.conf import settings


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


def plugin_update_snapshot() -> Dict[str, Any]:
    try:
        from postpress_ai.models.plugin_release import PluginRelease
    except Exception:
        return {
            "available": False,
            "latest_version": "",
            "download_url": None,
            "filename": "",
            "changelog": "",
            "released_at": None,
        }

    rel = (
        PluginRelease.objects.filter(product_slug="postpress-ai", is_active=True)
        .order_by("-released_at", "-id")
        .first()
    )

    if not rel:
        return {
            "available": False,
            "latest_version": "",
            "download_url": None,
            "filename": "",
            "changelog": "",
            "released_at": None,
        }

    raw_url = None
    try:
        raw_url = rel.zip_file.url if getattr(rel, "zip_file", None) else None
    except Exception:
        raw_url = None

    download_url = None
    base = _opt_str(getattr(settings, "DEPLOY_BASE_URL", None)) or _opt_str(os.environ.get("DEPLOY_BASE_URL"))

    if raw_url:
        raw_url = str(raw_url).strip()
        if raw_url.startswith("http://") or raw_url.startswith("https://"):
            download_url = raw_url
        elif base:
            if not raw_url.startswith("/"):
                raw_url = "/" + raw_url
            download_url = base.rstrip("/") + raw_url

    filename = _opt_str(getattr(rel, "filename", None))
    if not filename:
        try:
            filename = os.path.basename(rel.zip_file.name or "")
        except Exception:
            filename = ""

    return {
        "available": True,
        "latest_version": _opt_str(getattr(rel, "version", None)) or "",
        "download_url": download_url,
        "filename": filename or "",
        "changelog": getattr(rel, "changelog", "") or "",
        "released_at": getattr(rel, "released_at", None),
    }
