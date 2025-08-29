from django.shortcuts import render, redirect
from humancapital.forms.personality_form import PersonalityForm
from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.personality import Personality


def personality_form(request):
    """
    Step 4: Capture personality traits (Big Five: OCEAN) for this session.
    - GET: Show the form
    - POST: Validate and save Personality tied to the session
    """

    # Ensure a session exists (otherwise bounce back)
    session_id = request.session.get("session_id")
    if not session_id:
        return redirect("personal_info")

    session = AssessmentSession.objects.get(id=session_id)

    if request.method == "POST":
        form = PersonalityForm(request.POST)
        if form.is_valid():
            personality = form.save(commit=False)
            personality.session = session
            personality.save()

            # Move forward to Behavior step
            return redirect("behavior_form")
    else:
        form = PersonalityForm()

    return render(request, "humancapital/personality.html", {"form": form})
