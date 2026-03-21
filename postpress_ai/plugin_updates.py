from __future__ import annotations

import os
from typing import Any, Dict, Optional

from django.conf import settings
from django.urls import reverse


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

    download_url = None
    base = _opt_str(getattr(settings, "DEPLOY_BASE_URL", None)) or _opt_str(os.environ.get("DEPLOY_BASE_URL"))

    try:
        download_path = reverse("postpress_ai:ppa-plugin-download")
    except Exception:
        download_path = None

    if download_path:
        download_path = str(download_path).strip()
        if download_path.startswith("http://") or download_path.startswith("https://"):
            download_url = download_path
        elif base:
            if not download_path.startswith("/"):
                download_path = "/" + download_path
            download_url = base.rstrip("/") + download_path
        else:
            download_url = download_path

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

