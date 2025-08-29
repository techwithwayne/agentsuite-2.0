from django.shortcuts import render, redirect
from humancapital.forms.behavior_form import BehaviorForm
from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.behavior import Behavior


def behavior_form(request):
    """
    Step 5: Capture behavioral style indicators for this session.
    Includes communication, decision-making, leadership, collaboration, conflict handling.
    - GET: Show the form
    - POST: Validate and save Behavior tied to the session
    """

    # Ensure a session exists
    session_id = request.session.get("session_id")
    if not session_id:
        return redirect("personal_info")

    session = AssessmentSession.objects.get(id=session_id)

    if request.method == "POST":
        form = BehaviorForm(request.POST)
        if form.is_valid():
            behavior = form.save(commit=False)
            behavior.session = session
            behavior.save()

            # Move forward to Motivation step
            return redirect("motivation_form")
    else:
        form = BehaviorForm()

    return render(request, "humancapital/behavior.html", {"form": form})
