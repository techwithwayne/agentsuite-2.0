import os
from django.conf import settings
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", None)))

DIAGNOSTIC_CATEGORIES = {
    "Performance": ["slow", "lag", "takes forever", "8 seconds", "load time"],
    "Design/Layout": ["broken", "misaligned", "mobile", "images", "fonts", "responsive"],
    "Functionality": ["form", "button", "submit", "not working", "doesn't work"],
    "Access/Errors": ["403", "404", "500", "white screen", "can't log in", "error"],
    "Update/Plugin": ["plugin", "update", "theme", "broke", "conflict"],
    "Security/Hack": ["hacked", "spam", "malware", "injected", "redirect"],
    "Hosting/DNS": ["dns", "hosting", "cloudflare", "propagation", "server"]
}

def classify_issue(user_input):
    prompt = f"""
You are a helpful support agent. Categorize the user's website issue into one of these diagnostic categories:
{", ".join(DIAGNOSTIC_CATEGORIES.keys())}

Respond in this format:
Category: <CATEGORY>
Confidence: <0–100>
ClarifyingQuestion: <QUESTION to understand issue better>

User Input:
\"{user_input}\"
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You classify website problems into categories and ask clarifying questions."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )
    result = response.choices[0].message.content.strip()
    lines = result.splitlines()
    category = "Unclassified"
    confidence = 0
    clarifying_question = "Can you describe the issue a bit more so I can help?"

    for line in lines:
        if line.startswith("Category:"):
            category = line.replace("Category:", "").strip()
        elif line.startswith("Confidence:"):
            try:
                confidence = int(line.replace("Confidence:", "").strip())
            except:
                confidence = 50
        elif line.startswith("ClarifyingQuestion:"):
            clarifying_question = line.replace("ClarifyingQuestion:", "").strip()

    return category, confidence, clarifying_question

def summarize_issue(history, category):
    user_messages = [m['content'] for m in history if m['role'] == 'user']
    summary_prompt = f"""
You are a helpful AI support agent. Summarize the user's issue based on this conversation in a friendly and clear way.

Category: {category}
Conversation:
{chr(10).join(user_messages)}

Respond in 1–3 sentences like a website doctor would explain it to the user.
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You summarize website problems conversationally, like a helpful doctor."},
            {"role": "user", "content": summary_prompt}
        ],
        temperature=0.6
    )
    return response.choices[0].message.content.strip()

def get_agent_response(history, stage="initial", category=None, clarifications=0):
    last_user_input = history[-1]['content'] if history else ""
    user_input = last_user_input.lower().strip()

    closing_phrases = ["thanks", "thank you", "bye", "goodbye", "that’s all", "got it", "appreciate it", "ok cool", "see ya", "nope", "i’m good"]
    if stage in ["offered_report", "report_sent"] and any(phrase in user_input for phrase in closing_phrases):
        return {
            "response": "You're very welcome! 😊 If you ever need more help, I’m just a click away. Take care!",
            "next_stage": "closed",
            "category": category,
            "clarifications": clarifications,
            "typing_delay": 3
        }

    if stage == "initial":
        category, confidence, question = classify_issue(last_user_input)
        if confidence >= 70:
            return {
                "response": question,
                "next_stage": "clarifying",
                "category": category,
                "clarifications": 1,
                "typing_delay": 4
            }
        else:
            return {
                "response": "Hmm, I’m not quite sure yet — could you describe that a bit differently?",
                "next_stage": "initial",
                "category": None,
                "clarifications": clarifications + 1,
                "typing_delay": 4
            }

    elif stage == "clarifying":
        if clarifications >= 2:
            summary = summarize_issue(history, category)
            return {
                "response": f"{summary} Would you like me to email you a full diagnostic report with tips to fix it?",
                "next_stage": "summarize",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }
        else:
            _, confidence, question = classify_issue(last_user_input)
            return {
                "response": question if confidence >= 70 else "Got it. I just need a little more info — what happens exactly when you try?",
                "next_stage": "clarifying",
                "category": category,
                "clarifications": clarifications + 1,
                "typing_delay": 4
            }

    elif stage == "summarize":
        if user_input in ["yes", "sure", "okay", "ok", "yep", "yeah"]:
            return {
                "response": "No problem. Just enter your name and email below to get a report. It's free and tailored to your issue.",
                "next_stage": "offered_report",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }
        elif user_input in ["no", "not now", "maybe later"]:
            return {
                "response": "Totally fine! If you change your mind, just let me know and I’ll prepare a report for you.",
                "next_stage": "summarize",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }
        else:
            return {
                "response": "Would you like me to email you a full diagnostic report with tips to fix it?",
                "next_stage": "summarize",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }

    elif stage == "offered_report":
        return {
            "response": "Awesome. Just fill out your name and email below and I’ll generate your custom report. 📬",
            "next_stage": "offered_report",
            "category": category,
            "clarifications": clarifications,
            "typing_delay": 4
        }

    return {
        "response": "Let’s take another look together. Could you explain a bit more?",
        "next_stage": "initial",
        "category": None,
        "clarifications": 0,
        "typing_delay": 4
    }
