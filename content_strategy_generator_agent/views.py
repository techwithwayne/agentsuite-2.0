# views.py
import os
import json
import markdown
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from .forms import StrategyRequestForm
from .models import StrategyRequest
from openai import OpenAI

# ✅ Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Existing form-based view (unchanged)
@csrf_exempt
def generate_strategy(request):
    result = None
    if request.method == 'POST':
        form = StrategyRequestForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            prompt = (
                f"Generate a 3-month blog content strategy for the following:\n"
                f"Niche: {instance.niche}\n"
                f"Goals: {instance.goals}\n"
                f"Tone: {instance.tone}\n"
                f"Include 12 weekly post titles, focus keywords, outlines with H2s, and suggested CTAs."
            )
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a content strategist AI agent."},
                        {"role": "user", "content": prompt}
                    ]
                )
                instance.result = response.choices[0].message.content
                instance.save()
                result = markdown.markdown(instance.result)
            except Exception as e:
                result = f"An error occurred while generating the strategy: {str(e)}"
    else:
        form = StrategyRequestForm()

    return render(request, 'content_strategy_generator_agent/generate_strategy.html', {
        'form': form,
        'result': result
    })

# ✅ New JSON-based view for AJAX
@csrf_exempt
def generate_strategy_json(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            prompt = (
                f"Generate a 3-month blog content strategy for the following:\n"
                f"Niche: {data.get('niche')}\n"
                f"Goals: {data.get('goals')}\n"
                f"Tone: {data.get('tone')}\n"
                f"Include 12 weekly post titles, focus keywords, outlines with H2s, and suggested CTAs."
            )
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a content strategist AI agent."},
                    {"role": "user", "content": prompt}
                ]
            )
            markdown_result = markdown.markdown(response.choices[0].message.content)
            return JsonResponse({"result": markdown_result})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method."}, status=400)
