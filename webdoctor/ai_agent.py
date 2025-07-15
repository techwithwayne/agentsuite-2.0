# ai_agent.py

import openai
import os
import json

# 🔑 Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 📁 Load irrelevant phrases once at startup
with open(os.path.join(os.path.dirname(__file__), "irrelevant_phrases.json")) as f:
    irrelevant_data = json.load(f)
irrelevant_keywords = irrelevant_data.get("irrelevant_phrases", [])

# 🧠 Website-related keywords that trigger "Doctor" mode
website_issue_keywords = [
    "wordpress", "site", "website", "plugin", "loading", "error", "broken",
    "dashboard", "page", "theme", "host", "domain", "ssl", "update", "redirect",
    "database", "server", "hosting", "caching", "maintenance"
]

# 🧠 This is the Website Doctor's upgraded system message
WEBSITE_DOCTOR_SYSTEM_PROMPT = """
You are 'Wayne, the Website Doctor' — a friendly, knowledgeable web dev expert who helps users fix website problems.

Your job:
- Greet the user warmly
- Explain clearly what’s likely going wrong
- Give 2–3 specific things they can check or try
- **ALWAYS end with a clarifying question** to continue the conversation

Use clean Markdown formatting.
Stay practical and supportive. Just a touch of humor is okay.
Avoid repeating the user’s question back at them.
NEVER end with generic lines like “let me know” or “tell me your issue.”
Never mention or refer to 'mom', 'mother', 'moms', or 'mothers'.
"""


# 🧠 This is your general casual Wayne prompt
CASUAL_SYSTEM_PROMPT = """
You reply like Wayne — a warm, helpful, confident tech expert with a teeny bit of humor and an urban edge.

Use one short paragraph (max 30 words), formatted in **Markdown** if useful.

Never mention or refer to 'mom', 'mother', 'moms', or 'mothers'. Never say you're an AI.
"""

def get_agent_response(message, context_convos=None, stage="initial"):
    if context_convos is None:
        context_convos = []

    base_messages = [
        {"role": "system", "content": "You are Wayne, the Website Doctor. You help people fix their websites in a clear, friendly, slightly humorous tone using Markdown. Never mention 'mom', 'mother', or similar words."}
    ] + context_convos

    if stage == "initial":
        user_prompt = (
            f"A user said: '{message}'. Greet them warmly and ask what issue they’re having with their website. "
            "Keep it casual and friendly. Use Markdown formatting where helpful."
        )
    elif stage == "clarifying":
        user_prompt = (
            f"A user said: '{message}'. Ask 2–3 real follow-up questions to better understand their problem. "
            "Examples: what platform they’re using, error message, when it started. Do not repeat 'tell me your issue' again. "
            "Just ask relevant clarifying questions in a helpful, concise tone."
        )

    elif stage == "summarize":
        user_prompt = (
            f"Summarize what the user has said so far across the conversation and confirm it in your words. "
            "Ask them if that summary is correct before proceeding. Be helpful and brief."
        )
    elif stage == "offered_report":
        user_prompt = (
            f"Ask the user kindly if they’d like a full written report emailed to them. "
            "If they say yes, let them know a form will appear. If they say no, offer a friendly nudge to book a free site review or consultation."
        )
    else:
        user_prompt = f"The user said: '{message}'. Help them politely with anything they need."

    full_messages = base_messages + [{"role": "user", "content": user_prompt}]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=full_messages,
        temperature=0.5,
    )

    return response.choices[0].message.content
