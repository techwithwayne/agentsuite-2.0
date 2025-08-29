from __future__ import annotations
import re
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import JsonResponse, HttpRequest
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import UserProfile

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _json_error(msg: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": msg}, status=status)

def _send_code_email(*, to_email: str, to_name: str | None, code: str) -> bool:
    subject = "Your Personal Mentor confirmation code"
    greet = to_name or "there"
    message = (
        f"Hi {greet},\n\n"
        f"Your confirmation code is: {code}\n"
        f"It expires in 20 minutes.\n\n"
        f"If you didn’t request this, you can ignore this email."
    )
    try:
        sent = send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            [to_email],
            fail_silently=False,
        )
        ok = sent == 1
        logger.info("Sent code email → %s ok=%s backend=%s", to_email, ok, settings.EMAIL_BACKEND)
        print(f"[Auth] Code email sent={ok} to {to_email} (backend={settings.EMAIL_BACKEND})")
        return ok
    except Exception as e:
        logger.exception("Failed sending code email to %s", to_email)
        print(f"[Auth] FAILED to send email to {to_email}: {e}")
        return False

@require_POST
def start_registration(request: HttpRequest) -> JsonResponse:
    """Create or reuse a user, store only first word in first_name, and send code."""
    name_input = (request.POST.get("name") or "").strip()
    first_name = name_input.split()[0] if name_input else ""
    email = (request.POST.get("email") or "").lower().strip()
    password = request.POST.get("password") or ""

    if not first_name or not email or not password:
        return _json_error("All fields are required.")
    if not EMAIL_RE.match(email):
        return _json_error("Please enter a valid email address.")

    user, created = User.objects.get_or_create(
        username=email,
        defaults={"email": email, "first_name": first_name}
    )
    if not created:
        # Update first_name opportunistically to first token
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            user.save(update_fields=["first_name"])
    else:
        user.set_password(password)
        user.save()

    prof, _ = UserProfile.objects.get_or_create(user=user)
    # Always (re-)issue a code on registration
    code = prof.issue_code()
    email_sent = _send_code_email(to_email=email, to_name=user.first_name, code=code)

    # Store pending email in session so /auth/confirm/ and /auth/resend/ know the target
    request.session["pending_email"] = email

    return JsonResponse({"ok": True, "next": "confirm", "email_sent": email_sent})

@require_POST
def confirm_code(request: HttpRequest) -> JsonResponse:
    """Verify a 6-digit code, mark verified, login, and allow API access."""
    email = (request.POST.get("email") or request.session.get("pending_email") or "").lower().strip()
    code = (request.POST.get("code") or "").strip()

    if not email or not code:
        return _json_error("Email and code are required.")

    try:
        user = User.objects.get(username=email)
    except User.DoesNotExist:
        return _json_error("Account not found.", status=404)

    prof, _ = UserProfile.objects.get_or_create(user=user)
    if not prof.code_valid(code):
        return _json_error("Invalid or expired code.", status=401)

    prof.verified_at = timezone.now()
    prof.save(update_fields=["verified_at"])

    login(request, user)
    request.session["mentor_verified"] = True
    request.session.pop("pending_email", None)
    logger.info("User %s confirmed and logged in", email)
    return JsonResponse({"ok": True})

@require_POST
def login_user(request: HttpRequest) -> JsonResponse:
    """Password login. If not verified, (re)send a code and go to confirm."""
    email = (request.POST.get("email") or "").lower().strip()
    password = request.POST.get("password") or ""
    if not email or not password:
        return _json_error("Email and password are required.")
    user = authenticate(request, username=email, password=password)
    if not user:
        return _json_error("Invalid credentials.", status=401)

    prof, _ = UserProfile.objects.get_or_create(user=user)
    if prof.needs_verification():
        # Issue new code and email it (no cooldown on login-triggered send)
        code = prof.issue_code()
        email_sent = _send_code_email(to_email=email, to_name=user.first_name, code=code)
        request.session["pending_email"] = email
        return JsonResponse({"ok": True, "next": "confirm", "email_sent": email_sent})

    login(request, user)
    request.session["mentor_verified"] = True
    logger.info("User %s logged in (already verified)", email)
    return JsonResponse({"ok": True})

@require_POST
def resend_code(request: HttpRequest) -> JsonResponse:
    """Resend a 6-digit code, respecting a 2-minute cooldown.

    Input:
      - optional 'email' (defaults to session['pending_email'])
    Output:
      { ok, cooldown_remaining_seconds, email_sent }
    """
    email = (request.POST.get("email") or request.session.get("pending_email") or "").lower().strip()
    if not email:
        return _json_error("No email in session; start with Register or Login.")

    try:
        user = User.objects.get(username=email)
    except User.DoesNotExist:
        return _json_error("Account not found.", status=404)

    prof, _ = UserProfile.objects.get_or_create(user=user)

    cooldown_remaining_seconds = 0
    if prof.last_resend_at:
        target = prof.last_resend_at + prof.RESEND_COOLDOWN
        now = timezone.now()
        if now < target:
            cooldown_remaining_seconds = int((target - now).total_seconds())

    if cooldown_remaining_seconds > 0:
        # Not allowed to resend yet
        return JsonResponse({"ok": True, "cooldown_remaining_seconds": cooldown_remaining_seconds, "email_sent": False})

    # Allowed to resend: issue a fresh code, send email, and mark resend time
    code = prof.issue_code()
    email_sent = _send_code_email(to_email=email, to_name=user.first_name, code=code)
    prof.mark_resend()

    # Recompute remaining (should be full cooldown)
    cooldown_remaining_seconds = int(prof.RESEND_COOLDOWN.total_seconds())
    request.session["pending_email"] = email

    return JsonResponse({"ok": True, "cooldown_remaining_seconds": cooldown_remaining_seconds, "email_sent": email_sent})
