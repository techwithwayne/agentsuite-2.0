# /opt/render/project/src/postpress_ai/urls/routes_legacy.py

from __future__ import annotations

from django.urls import re_path  # CHANGED:
from postpress_ai import views as ppa_views

app_name = "postpress_ai"

urlpatterns = [
    # Accept both /x and /x/ (prevents 301 from APPEND_SLASH + CommonMiddleware).  # CHANGED:
    re_path(r"health/?$", ppa_views.health, name="ppa-health"),  # CHANGED:
    re_path(r"version/?$", ppa_views.version, name="ppa-version"),  # CHANGED:
    re_path(r"preview/?$", ppa_views.preview, name="ppa-preview"),  # CHANGED:
    re_path(r"store/?$", ppa_views.store, name="ppa-store"),  # CHANGED:
    re_path(r"preview/debug-model/?$", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),  # CHANGED:

    # Support widget endpoints (WP Admin → Django)  # CHANGED:
    re_path(r"support/chat/?$", ppa_views.support_chat, name="ppa-support-chat"),  # CHANGED:
    re_path(r"support/account_status/?$", ppa_views.support_account_status, name="ppa-support-account-status"),  # CHANGED:
    re_path(r"support/action/create_checkout/?$", ppa_views.support_action_create_checkout, name="ppa-support-create-checkout"),  # CHANGED:
    re_path(r"support/action/create_billing_portal/?$", ppa_views.support_action_create_billing_portal, name="ppa-support-billing-portal"),  # CHANGED:
    re_path(r"support/action/issue_license_key/?$", ppa_views.support_action_issue_license_key, name="ppa-support-issue-license-key"),  # CHANGED:
    re_path(r"support/action/replace_license_key/?$", ppa_views.support_action_replace_license_key, name="ppa-support-replace-license-key"),  # CHANGED:
    re_path(r"support/action/refund/?$", ppa_views.support_action_refund, name="ppa-support-refund"),  # CHANGED:
]