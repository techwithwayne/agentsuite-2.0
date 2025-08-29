from django.shortcuts import render, redirect
from humancapital.forms.motivation_form import MotivationForm
from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.motivation import Motivation


def motivation_form(request):
    """
    Step 6: Capture motivational drivers for this session.
    Includes achievement, stability, autonomy, recognition, and learning.
    - GET: Show the form
    - POST: Validate and save Motivation tied to the session
    """

    # Ensure a session exists
    session_id = request.session.get("session_id")
    if not session_id:
        return redirect("personal_info")

    session = AssessmentSession.objects.get(id=session_id)

    if request.method == "POST":
        form = MotivationForm(request.POST)
        if form.is_valid():
            motivation = form.save(commit=False)
            motivation.session = session
            motivation.save()

            # Move forward to Summary step
            return redirect("summary_view")
    else:
        form = MotivationForm()

    return render(request, "humancapital/motivation.html", {"form": form})
