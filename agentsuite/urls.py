# /home/techwithwayne/agentsuite/agentsuite/urls.py
"""
CHANGE LOG
----------
2025-12-24
- ADD: Project-level /postpress-ai/license/* endpoints before include() for precedence.  # CHANGED:
       activate/verify/deactivate → postpress_ai.views.license (Django authoritative). # CHANGED:
- ADD: Project-level /postpress-ai/license/debug-auth/ endpoint before include() for precedence.  # CHANGED:
       debug-auth → postpress_ai.views.debug_model.license_debug_auth (safe booleans only).       # CHANGED:
- FIX: Normalize change markers in this file to use '# CHANGED:' consistently.  # CHANGED:

2025-12-26
- ADD: Project-level /postpress-ai/stripe/webhook/ endpoint before include() for precedence.  # CHANGED:
       Stripe is fulfillment-only (payment -> issue key), WP never talks to Stripe.            # CHANGED:

2025-12-27
- ADD: Project-level /postpress-ai/stripe/checkout/create/ endpoint to stop 404.              # CHANGED:
       Checkout create must be project-level for precedence; returns Stripe Checkout URL.     # CHANGED:

2025-11-10
- ADD: Root-level aliases /preview/ and /store/ → canonical postpress_ai views.          # CHANGED:
- KEEP: Direct /postpress-ai/store/ override precedence and /postpress-ai include.       # CHANGED:

2025-10-30
- ADD: Inline /postpress-ai/health/ and /postpress-ai/version/ endpoints placed before include()
       so they resolve first without modifying app files.
- NOTE: Keep endpoints minimal for readiness checks; no extra imports elsewhere.

2025-10-24
- FIX: Map PostPress AI via include("postpress_ai.urls", namespace="postpress_ai") to avoid missing-module errors.
- FIX: Guard optional include("apps.api.urls") so environments without 'apps' do not 500.

2026-02-22
- FIX: Eliminate 301 redirects for missing trailing slash on critical PostPress endpoints.    # CHANGED:
       WordPress POSTs can lose body/headers across 301. Add no-slash alias routes that      # CHANGED:
       internally dispatch to the canonical trailing-slash endpoint without redirecting.     # CHANGED:
"""

# /home/techwithwayne/agentsuite/agentsuite/urls.py
"""
CHANGE LOG
----------
2025-12-27
- FIX: Correct import path for Stripe checkout session view.
       checkout_session.py lives directly under postpress_ai.views (not views.stripe).  # CHANGED:
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include, re_path, resolve  # CHANGED:

from postpress_ai import views as ppa_views
from postpress_ai.views.store import store_view

from postpress_ai.views.license import (
    license_activate,
    license_verify,
    license_deactivate,
)

from postpress_ai.views.debug_model import license_debug_auth
from postpress_ai.views.stripe_webhook import stripe_webhook

# ✅ FIXED IMPORT PATH  # CHANGED:
from postpress_ai.views.checkout_session import create_checkout_session  # CHANGED:

from webdoctor import views as webdoctor_views
from barista_assistant.views import success_view


def ppa_health_view(request):
    return JsonResponse({"ok": True})


def ppa_version_view(request):
    return JsonResponse({"version": "postpress-ai.v2.1-2025-10-30"})


def _alias_to(canonical_path: str):
    """
    Internal no-slash alias dispatcher (NO redirects).                                  # CHANGED:
    Why: WP HTTP clients can drop POST body/headers when a 301 appends '/'.             # CHANGED:
    This view rewrites request.path/path_info in-memory and dispatches to the canonical # CHANGED:
    trailing-slash endpoint via django.urls.resolve().                                  # CHANGED:
    """
    def _view(request, *args, **kwargs):  # noqa: ARG001
        orig_path = getattr(request, "path", "")
        orig_path_info = getattr(request, "path_info", "")
        orig_meta_path_info = request.META.get("PATH_INFO")
        orig_meta_request_uri = request.META.get("REQUEST_URI")

        try:
            # Pretend the request arrived at the canonical URL so downstream logic
            # (headers/logging/build_absolute_uri/etc.) behaves consistently.           # CHANGED:
            request.path = canonical_path
            request.path_info = canonical_path
            request.META["PATH_INFO"] = canonical_path
            # Keep querystring if present.
            if request.META.get("QUERY_STRING"):
                request.META["REQUEST_URI"] = canonical_path + "?" + request.META["QUERY_STRING"]
            else:
                request.META["REQUEST_URI"] = canonical_path

            match = resolve(canonical_path)
            return match.func(request, *match.args, **match.kwargs)
        finally:
            # Restore request to original values to avoid confusing later middleware.  # CHANGED:
            request.path = orig_path
            request.path_info = orig_path_info
            if orig_meta_path_info is None:
                request.META.pop("PATH_INFO", None)
            else:
                request.META["PATH_INFO"] = orig_meta_path_info
            if orig_meta_request_uri is None:
                request.META.pop("REQUEST_URI", None)
            else:
                request.META["REQUEST_URI"] = orig_meta_request_uri

    return _view


urlpatterns = [
    # -------------------------------------------------------------------------
    # NO-SLASH ALIASES (stop 301 redirects; preserve POST body/headers)         # CHANGED:
    # -------------------------------------------------------------------------
    re_path(r"^preview$", _alias_to("/preview/")),  # CHANGED:
    re_path(r"^store$", _alias_to("/store/")),      # CHANGED:

    re_path(r"^postpress-ai/health$", _alias_to("/postpress-ai/health/")),  # CHANGED:
    re_path(r"^postpress-ai/version$", _alias_to("/postpress-ai/version/")),  # CHANGED:

    re_path(r"^postpress-ai/preview$", _alias_to("/postpress-ai/preview/")),  # CHANGED:
    re_path(r"^postpress-ai/generate$", _alias_to("/postpress-ai/generate/")),  # CHANGED:
    re_path(r"^postpress-ai/store$", _alias_to("/postpress-ai/store/")),  # CHANGED:

    re_path(r"^postpress-ai/license/activate$", _alias_to("/postpress-ai/license/activate/")),  # CHANGED:
    re_path(r"^postpress-ai/license/verify$", _alias_to("/postpress-ai/license/verify/")),  # CHANGED:
    re_path(r"^postpress-ai/license/deactivate$", _alias_to("/postpress-ai/license/deactivate/")),  # CHANGED:
    re_path(r"^postpress-ai/license/debug-auth$", _alias_to("/postpress-ai/license/debug-auth/")),  # CHANGED:

    re_path(r"^postpress-ai/stripe/webhook$", _alias_to("/postpress-ai/stripe/webhook/")),  # CHANGED:
    re_path(r"^postpress-ai/stripe/checkout/create$", _alias_to("/postpress-ai/stripe/checkout/create/")),  # CHANGED:

    # -------------------------------------------------------------------------
    # CANONICAL ROUTES (trailing slash versions)                               # CHANGED:
    # -------------------------------------------------------------------------
    path("preview/", ppa_views.preview, name="ppa-preview-root"),
    path("store/", ppa_views.store, name="ppa-store-root"),

    path("postpress-ai/store/", store_view, name="ppa_store_direct"),

    path("postpress-ai/license/activate/", license_activate),
    path("postpress-ai/license/verify/", license_verify),
    path("postpress-ai/license/deactivate/", license_deactivate),

    path("postpress-ai/license/debug-auth/", license_debug_auth),

    path("postpress-ai/stripe/webhook/", stripe_webhook),

    # ✅ Stripe Checkout Create (now import-safe)
    path(
        "postpress-ai/stripe/checkout/create/",
        create_checkout_session,
        name="ppa_stripe_checkout_create",
    ),

    path("postpress-ai/health/", ppa_health_view),
    path("postpress-ai/version/", ppa_version_view),

    path("admin/", admin.site.urls),

    path("agent/", include("webdoctor.urls")),
    path("webdoctor/", webdoctor_views.webdoctor_home),
    path("tools/", include("promptopilot.urls")),

    path("website-analyzer/", include("website_analyzer.urls")),

    path("barista-assistant/", include("barista_assistant.urls")),
    path("api/", include("barista_assistant.api_urls")),
    path("api/menu/", include("barista_assistant.menu.urls")),
    path("success/", success_view),

    path("content-strategy/", include("content_strategy_generator_agent.urls")),
    path("personal-mentor/", include("personal_mentor.urls", namespace="personal_mentor")),

    path("postpress-ai/", include("postpress_ai.urls", namespace="postpress_ai")),
]


# === Optional/Monorepo routes (guarded) ============================================
# Some deployments do not have the 'apps' package checked out; include only if importable.
try:
    import importlib
    importlib.import_module("apps.api.urls")
except ModuleNotFoundError:
    import sys
    sys.stderr.write("[urls] Optional 'apps.api.urls' not present; skipping /reclaimr/ route\n")
else:
    urlpatterns.append(path("reclaimr/", include("apps.api.urls")))