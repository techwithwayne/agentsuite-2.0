from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from webdoctor.models import UserInteraction, AgentResponse, DiagnosticReport
from webdoctor.ai_agent import get_agent_response
import json
import re

def widget_frame(request):
    return render(request, "webdoctor/widget_frame.html")

def webdoctor_home(request):
    return render(request, 'webdoctor/chat_widget.html')

@csrf_exempt
def chat_widget(request):
    return render(request, 'webdoctor/chat_widget.html')

@csrf_exempt
def handle_message(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        message = data.get('message', '')
        lang = data.get('lang', 'en')

        session = request.session
        conversation = session.get("conversation", {
            "history": [],
            "stage": "initial",
            "category": None,
            "clarifications": 0
        })

        # Store current user message
        conversation["history"].append({"role": "user", "content": message})

        # Get AI-generated response
        ai_response = get_agent_response(
            history=conversation["history"],
            stage=conversation["stage"],
            category=conversation["category"],
            clarifications=conversation["clarifications"],
            lang=lang
        )

        # Update session state
        conversation["history"].append({"role": "assistant", "content": ai_response["response"]})
        conversation["stage"] = ai_response["next_stage"]
        conversation["category"] = ai_response.get("category", conversation["category"])
        conversation["clarifications"] = ai_response.get("clarifications", conversation["clarifications"])
        session["conversation"] = conversation
        session.modified = True

        # Store response if unique
        AgentResponse.get_or_create_response(ai_response["response"])

        return JsonResponse({
            "response": ai_response["response"],
            "typing_delay": ai_response.get("typing_delay", 4),
            "stage": ai_response.get("next_stage", "initial")
        })

    return JsonResponse({'error': 'Invalid method'}, status=400)

@csrf_exempt
def submit_form(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        email = data.get('email')
        issue = data.get('issue')

        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            return JsonResponse({'error': 'Invalid email format'}, status=400)

        UserInteraction.objects.create(name=name, email=email, issue_description=issue)

        report_content = (
            f"Diagnostic Report for {name}\n"
            f"Issue: {issue}\n"
            f"Suggested Actions: Check hosting performance, optimize images, or contact Wayne’s team for a free consultation."
        )

        DiagnosticReport.objects.create(
            user_email=email,
            issue_details=issue,
            report_content=report_content
        )

        return JsonResponse({'message': 'Report sent to your email!'})

    return JsonResponse({'error': 'Invalid method'}, status=400)