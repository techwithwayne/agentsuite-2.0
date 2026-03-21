from __future__ import annotations

import os

from django.http import FileResponse, Http404
from postpress_ai.models.plugin_release import PluginRelease


def plugin_download_view(request):
    rel = (
        PluginRelease.objects.filter(product_slug="postpress-ai", is_active=True)
        .order_by("-released_at", "-id")
        .first()
    )

    if not rel or not getattr(rel, "zip_file", None):
        raise Http404("No active plugin release.")

    try:
        rel.zip_file.open("rb")
    except Exception as exc:
        raise Http404("Plugin file not found.") from exc

    try:
        filename = os.path.basename(rel.zip_file.name or "") or "postpress-ai.zip"
    except Exception:
        filename = "postpress-ai.zip"

    return FileResponse(rel.zip_file, as_attachment=True, filename=filename)
