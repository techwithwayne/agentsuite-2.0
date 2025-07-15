import os
from django.shortcuts import render
from .forms import StrategyRequestForm
from .models import StrategyRequest
from openai import OpenAI

import markdown

# ✅ Initialize OpenAI client correctly (replaces openai.api_key)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_strategy(request):
    result = None

    if request.method == 'POST':
        form = StrategyRequestForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)

            # ✅ Clear, structured prompt
            prompt = (
                f"Generate a 3-month blog content strategy for the following:\n"
                f"Niche: {instance.niche}\n"
                f"Goals: {instance.goals}\n"
                f"Tone: {instance.tone}\n"
                f"Include 12 weekly post titles, focus keywords, outlines with H2s, and suggested CTAs."
            )

            try:
                # ✅ Correct client call per latest SDK
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
                # ✅ Adds visible error feedback for debugging
                result = f"An error occurred while generating the strategy: {str(e)}"

    else:
        form = StrategyRequestForm()

    return render(request, 'content_strategy_generator_agent/generate_strategy.html', {
        'form': form,
        'result': result
    })
