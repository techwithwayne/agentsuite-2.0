# views.py
# Handles the web interface and user message posting

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from personal_coach.assistant import create_thread, send_message

import json

@csrf_exempt
def chat_widget(request):
    # Loads the chat UI page
    return render(request, "personal_ai/chat.html")

@csrf_exempt
def handle_message(request):
    if request.method == "POST":
        data = json.loads(request.body)
        message = data.get("message", "")

        # For now, create a new thread on each message
        thread_id = create_thread()

        # Send the user message to the assistant and get response
        messages = send_message(thread_id, message)

        # Grab the assistant's last message only
        response_text = ""
        for msg in messages.data:
            if msg.role == "assistant":
                response_text = msg.content[0].text.value
                break

        return JsonResponse({"reply": response_text})
    return JsonResponse({"error": "Invalid request"}, status=400)
