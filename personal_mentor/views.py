import os
import json
import traceback
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .assistant import (
    run_assistant_conversation,
    messages_preview,  # safe preview helper
)

VIEWS_VERSION = "views.v2025-08-11-fixed-01"


def chat_view(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "personal_mentor/chat.html",
        {
            "version": VIEWS_VERSION,
            "debug": settings.DEBUG,
        },
    )


@csrf_exempt
def api_send(request: HttpRequest) -> JsonResponse:
    """
    Robust send endpoint: never 500s; returns a friendly message on any failure.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST required."}, status=405)

    # Parse body safely
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    user_text = (payload.get("message") or "").strip()
    if not user_text:
        return JsonResponse(
            {"ok": False, "message": "Tell me what you want to build and I’ll jump in."},
            status=200,
        )

    thread_id = request.session.get("personal_mentor_thread_id")

    try:
        result = run_assistant_conversation(user_text=user_text, thread_id=thread_id)

        # Persist thread id
        if result.get("thread_id"):
            request.session["personal_mentor_thread_id"] = result["thread_id"]
            request.session.modified = True

        reply = (result.get("reply") or "").strip()
        if not reply or reply in {"(No reply)", "(No content returned.)", "(empty)", "(null)"}:
            reply = (
                "I didn’t get a readable response there. Give me one concrete detail "
                "(stack, feature, or example) and I’ll get specific."
            )

        return JsonResponse(
            {
                "ok": True,
                "message": reply,
                "thread_id": result.get("thread_id"),
                "meta": {**result.get("meta", {}), "version": VIEWS_VERSION},
            },
            status=200,
        )
    except Exception as e:
        # Final shield: user gets friendly text, you keep a code & optional trace in DEBUG
        return JsonResponse(
            {
                "ok": False,
                "message": "The mentor hit an unexpected snag. Try once more in a sec.",
                "code": "send.unexpected",
                "detail": str(e) if settings.DEBUG else "",
                "trace": traceback.format_exc() if settings.DEBUG else "",
                "version": VIEWS_VERSION,
            },
            status=200,
        )


@csrf_exempt
def api_reset(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST required."}, status=405)
    request.session.pop("personal_mentor_thread_id", None)
    request.session.modified = True
    return JsonResponse({"ok": True, "message": "Fresh start."}, status=200)


def api_health(request: HttpRequest) -> JsonResponse:
    key_present = bool(os.getenv("OPENAI_API_KEY"))
    a_id_present = bool(
        os.getenv("PERSONAL_MENTOR_ASSISTANT_ID") or os.getenv("OPENAI_ASSISTANT_ID")
    )
    return JsonResponse(
        {
            "ok": True,
            "OPENAI_API_KEY_present": key_present,
            "PERSONAL_MENTOR_ASSISTANT_ID_present": a_id_present,
            "debug": settings.DEBUG,
            "version": VIEWS_VERSION,
        },
        status=200,
    )


def api_debug_messages(request: HttpRequest) -> JsonResponse:
    try:
        tid = request.session.get("personal_mentor_thread_id")
        if not tid:
            return JsonResponse({"thread_id": None, "messages": []})
        msgs = messages_preview(tid, limit=8)
        return JsonResponse({"thread_id": tid, "messages": msgs})
    except Exception as e:
        return JsonResponse(
            {
                "ok": False,
                "message": "Could not fetch messages preview.",
                "code": "debug.unexpected",
                "detail": str(e) if settings.DEBUG else "",
            },
            status=200,
        )
