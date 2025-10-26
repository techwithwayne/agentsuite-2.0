"""
PostPress AI — views package initializer (final, production)

Exports only the canonical public views and ensures the legacy symbol
`store` points to the normalize-only `store_view`.

If an optional view module is missing, we expose a small 501 fallback so
URLConfs that import by name don't explode at import time.
"""
from __future__ import annotations

from typing import Callable
from django.http import JsonResponse, HttpRequest, HttpResponse

def _fallback(name: str) -> Callable[[HttpRequest], HttpResponse]:
    def _view(_req: HttpRequest) -> HttpResponse:
        return JsonResponse({"ok": False, "error": f"view-missing:{name}", "ver": "1"}, status=501)
    _view.__name__ = name
    return _view

# --- canonical exports ---------------------------------------------------------

# health (optional)
try:
    from .health import health_view as health  # type: ignore
except Exception:
    health = _fallback("health")

# version (optional)
try:
    from .version import version_view as version  # type: ignore
except Exception:
    version = _fallback("version")

# preview (normalize-only; required for /postpress-ai/preview/)
try:
    from .preview import preview_view as preview  # type: ignore
except Exception:
    preview = _fallback("preview")

# preview_debug_model (optional)
try:
    from .preview_debug_model import preview_debug_model_view as preview_debug_model  # type: ignore
except Exception:
    preview_debug_model = _fallback("preview_debug_model")

# store (normalize-only; legacy public name `store`)
from .store import store_view as store  # critical: legacy symbol -> normalize-only handler

__all__ = ["health", "version", "preview", "preview_debug_model", "store"]

