"""
license.py  Support/activation assistant router for agentsuite-2.0

Goal:
- Provide deterministic, fast support replies (no external deps required).
- Offer suggested actions that your frontend/widget can wire up.
- Detect common UI events (popup blocked, something looks wrong).
"""
from __future__ import annotations

import json
import re
import textwrap
import uuid
from typing import Any, Dict

from settings import SETTINGS, as_bool

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _read_file(path: str, fallback: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return fallback


SYSTEM_PROMPT = _read_file("system_prompt.txt", "")
KNOWLEDGE_PACK = _read_file("knowledge-pack.md", "")


def is_email(s: str) -> bool:
    return bool(s and EMAIL_RE.match(s.strip()))


def normalize_site_url(site_url: str) -> str:
    site_url = (site_url or "").strip()
    if site_url.endswith("/"):
        site_url = site_url[:-1]
    return site_url


def something_looks_wrong(payload: Dict[str, Any]) -> bool:
    ui_event = (payload.get("ui_event") or payload.get("event") or "").strip().lower()
    if ui_event in ("something_looks_wrong", "something looks wrong"):
        return True

    sa = (payload.get("suggested_action_id") or payload.get("suggested_action") or "").strip().lower()
    return sa in ("something_looks_wrong", "something looks wrong")


def popup_blocked(payload: Dict[str, Any]) -> bool:
    ui_event = (payload.get("ui_event") or payload.get("event") or "").strip().lower()
    return ui_event in ("popup_blocked", "popup blocked") or as_bool(payload.get("popup_blocked"))


def action_resend(email: str = "", site_url: str = "", license_key_prefix: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if email:
        payload["email"] = email
    if site_url:
        payload["site_url"] = site_url
    if license_key_prefix:
        payload["license_key_prefix"] = license_key_prefix
    return {"type": "resend_activation_key", "label": "Resend activation email", "payload": payload}


def action_collect_verification() -> Dict[str, Any]:
    return {
        "type": "collect_verification",
        "label": "Provide checkout email + site URL + license prefix",
        "payload": {"email": "", "site_url": "", "license_key_prefix": ""},
    }


def action_escalate(reason: str = "", conversation_id: str = "") -> Dict[str, Any]:
    subject = "PostPress AI Support  Help needed"
    if reason:
        subject = f"PostPress AI Support  {reason}"[:120]
    payload = {
        "to": SETTINGS.SUPPORT_EMAIL,
        "subject": subject,
        "body": "Describe what happened and include: checkout email, site URL, and license key prefix.",
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return {"type": "escalate_to_support", "label": "Email support", "payload": payload}


def action_download() -> Dict[str, Any]:
    return {"type": "open_download_link", "label": "Open plugin download link", "payload": {"url": SETTINGS.PPA_PLUGIN_DOWNLOAD_URL}}


def infer_intent(message: str, payload: Dict[str, Any]) -> str:
    action = payload.get("action")
    if isinstance(action, dict) and action.get("type"):
        return str(action["type"])

    m = (message or "").lower()

    if any(k in m for k in ["resend", "didn't get", "didnt get", "never got", "no email", "missing email"]):
        return "resend_activation_key"

    if any(k in m for k in ["install", "upload plugin", "zip", "plugin upload"]):
        return "install_help"

    if any(k in m for k in ["refund", "charged", "billing", "invoice", "stripe"]):
        return "billing_help"

    if any(k in m for k in ["activation", "license", "key", "activate"]):
        return "activation_help"

    return "general_help"


def _extract_ctx(payload: Dict[str, Any]) -> Dict[str, Any]:
    ctx = payload.get("context") or {}
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            ctx = {"raw": ctx}
    if not isinstance(ctx, dict):
        ctx = {}

    if "site_url" in ctx:
        ctx["site_url"] = normalize_site_url(str(ctx.get("site_url") or ""))

    body_classes = ctx.get("body_classes")
    if isinstance(body_classes, str):
        ctx["body_classes"] = [c for c in body_classes.split() if c]
    elif not isinstance(body_classes, list):
        ctx["body_classes"] = []

    return ctx


def _context_banner(ctx: Dict[str, Any]) -> str:
    bits = []
    if ctx.get("page_kind"):
        bits.append(f"page={ctx['page_kind']}")
    if ctx.get("site_url"):
        bits.append(f"site={ctx['site_url']}")
    return f"(Context: {', '.join(bits)})\n\n" if bits else ""


def handle_support_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    message = str(payload.get("message") or "").strip()
    conversation_id = str(payload.get("conversation_id") or "").strip() or str(uuid.uuid4())
    ctx = _extract_ctx(payload)

    if popup_blocked(payload):
        msg = _context_banner(ctx) + textwrap.dedent(
            f"""
            Looks like your browser blocked a popup.

            Quick fixes:
            - Allow pop-ups for this site (browser site settings)
            - Try Incognito/Private mode (disables extensions)
            - Disable ad-blockers temporarily

            If it still fails, Ill escalate this to a human so we can get you a direct link.
            """
        ).strip()
        return {
            "conversation_id": conversation_id,
            "assistant_message": msg,
            "suggested_actions": [action_download(), action_escalate("Popup blocked", conversation_id)],
            "escalation_offered": True,
        }

    if something_looks_wrong(payload):
        msg = _context_banner(ctx) + textwrap.dedent(
            """
            Got it  something looks wrong usually means a blocked request, stale cache, or a mismatch in email/site info.

            Fast checks:
            - Refresh + try again
            - Try Incognito (extensions often break checkout/download)
            - Confirm your checkout email + site URL are correct

            If you paste your checkout email + site URL, I can route you to the exact fix  or escalate immediately.
            """
        ).strip()
        return {
            "conversation_id": conversation_id,
            "assistant_message": msg,
            "suggested_actions": [action_collect_verification(), action_escalate("Something looks wrong", conversation_id)],
            "escalation_offered": True,
        }

    if not message:
        starter = KNOWLEDGE_PACK or "PostPress AI Support: Tell me what you need help with (activation, install, billing)."
        return {
            "conversation_id": conversation_id,
            "assistant_message": starter,
            "suggested_actions": [action_resend(), action_escalate("Need help", conversation_id)],
            "escalation_offered": True,
        }

    intent = infer_intent(message, payload)

    if intent == "billing_help":
        msg = _context_banner(ctx) + textwrap.dedent(
            f"""
            For billing/refunds/charges, Ill get you to a human fast.

            Email **{SETTINGS.SUPPORT_EMAIL}** with:
            - Checkout email
            - Approx purchase date/time
            - What happened (charged twice / refund request / invoice needed)

            If you paste the checkout email + site URL here first, I can include it in the escalation.
            """
        ).strip()
        return {
            "conversation_id": conversation_id,
            "assistant_message": msg,
            "suggested_actions": [action_escalate("Billing", conversation_id)],
            "escalation_offered": True,
        }

    if intent == "install_help":
        msg = _context_banner(ctx) + textwrap.dedent(
            f"""
            Heres the fast install path:

            1) Download the plugin ZIP: {SETTINGS.PPA_PLUGIN_DOWNLOAD_URL}
            2) WordPress  Plugins  Add New  **Upload Plugin**
            3) Upload ZIP  Activate
            4) Paste your license key when prompted

            If anything blocks you, tell me what step youre on and what you see.
            """
        ).strip()
        return {
            "conversation_id": conversation_id,
            "assistant_message": msg,
            "suggested_actions": [action_download(), action_escalate("Install help", conversation_id)],
            "escalation_offered": True,
        }

    if intent in ("activation_help", "resend_activation_key"):
        msg = _context_banner(ctx) + textwrap.dedent(
            """
            I can help with activation.

            If you didnt receive the activation email, I can resend it  I just need:
            - Checkout email (the one you paid with)
            - Site URL (exact domain)
            - License key prefix (first 610 chars), if you have it

            Hit Resend activation email once you have the email ready.
            """
        ).strip()
        return {
            "conversation_id": conversation_id,
            "assistant_message": msg,
            "suggested_actions": [action_resend(), action_collect_verification(), action_escalate("Activation help", conversation_id)],
            "escalation_offered": True,
        }

    msg = _context_banner(ctx) + textwrap.dedent(
        """
        I can help with:
        - Resending your activation email
        - Installing PostPress AI
        - Verifying your purchase

        Tell me what youre trying to do  or hit Resend activation email if youre stuck.
        """
    ).strip()
    return {
        "conversation_id": conversation_id,
        "assistant_message": msg,
        "suggested_actions": [action_resend(), action_escalate("General help", conversation_id)],
        "escalation_offered": True,
    }
