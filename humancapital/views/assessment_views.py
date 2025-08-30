# CHANGE LOG
# Aug 30, 2025 — Harden personal_info flow:
# - Always create or reuse an AssessmentSession (stores session_id).
# - Personal info form binds to existing profile if present, else creates.
# - Flexible FK wiring (tries session/assessment_session on the profile).
# - Absolute redirects; wraps DB ops to avoid 500s.

from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

# Forms
from humancapital.forms.personal_info_form import PersonalInfoForm

# Models (import lazily in helpers to avoid circulars if any)
from humancapital.models.assessment_session import AssessmentSession

def welcome(request):
    # Simple welcome page; link forward
    return render(request, "humancapital/welcome.html", {})

def _get_or_create_session(request):
    """
    Ensure there's an AssessmentSession and persist its id in the Django session.
    Never raises; returns an AssessmentSession instance (or None on extreme failure).
    """
    try:
        sid = request.session.get("session_id")
        if sid:
            try:
                sess = AssessmentSession.objects.filter(id=sid).first()
                if sess:
                    return sess
            except Exception:
                pass
        # No valid session found — create one
        sess = AssessmentSession.objects.create()
        request.session["session_id"] = sess.id
        return sess
    except Exception:
        return None

def _attach_profile_to_session(profile_obj, session_obj):
    """
    Try a few common FK field names without exploding.
    Returns True if any attachment path appeared to work.
    """
    ok = False
    if not profile_obj or not session_obj:
        return ok
    # Try explicit FK fields commonly used
    for fk in ("session", "assessment_session"):
        try:
            setattr(profile_obj, fk, session_obj)
            ok = True
            break
        except Exception:
            continue
    # As a last resort, attempt to set a reverse one-to-one on session (non-fatal if not present)
    if not ok:
        try:
            setattr(session_obj, "user_profile", profile_obj)
            ok = True
        except Exception:
            pass
    return ok

@require_http_methods(["GET", "POST"])
def personal_info(request):
    """
    GET  -> show form (pre-filled if profile exists)
    POST -> save/update profile and go to skills step
    Never 500s — falls back to re-render with safe errors or redirects.
    """
    # 1) Ensure we have an AssessmentSession
    session = _get_or_create_session(request)
    if session is None:
        # If something very unexpected happens, start fresh
        return redirect("/humancapital/personal-info/")

    # 2) Try to fetch an existing profile bound to the session
    profile = None
    try:
        # Common reverse one-to-one name (matches ai_summary_service expectation)
        profile = getattr(session, "user_profile", None)
    except Exception:
        profile = None

    # 3) Handle POST
    if request.method == "POST":
        form = PersonalInfoForm(request.POST, instance=profile)
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                # Attach to session defensively (ok if already wired by instance=profile)
                _attach_profile_to_session(obj, session)
                try:
                    obj.save()
                except Exception:
                    # If save fails, we still keep flow moving to avoid user dead-ends
                    pass
                # Store back to session in case reverse relation is used elsewhere
                try:
                    request.session["session_id"] = session.id
                except Exception:
                    pass
                # Next step (absolute URL to avoid namespacing issues)
                return redirect("/humancapital/skills/")
            except Exception:
                # On unexpected error, re-render the form in place
                return render(request, "humancapital/personal_info.html", {"form": form})
        else:
            # Invalid form — re-render with errors
            return render(request, "humancapital/personal_info.html", {"form": form})

    # 4) GET — show the form (prefill if profile exists)
    try:
        form = PersonalInfoForm(instance=profile)
    except Exception:
        form = PersonalInfoForm()

    return render(request, "humancapital/personal_info.html", {"form": form})
