import openai
import os
import json

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load irrelevant phrases once at startup
with open(os.path.join(os.path.dirname(__file__), "irrelevant_phrases.json")) as f:
    irrelevant_data = json.load(f)
irrelevant_keywords = irrelevant_data.get("irrelevant_phrases", [])

# Keywords indicating a website issue
website_issue_keywords = [
    "wordpress", "site", "website", "plugin", "loading", "error", "broken",
    "dashboard", "page", "theme", "host", "domain", "ssl", "update", "redirect",
    "database", "server", "hosting", "caching", "maintenance"
]

def get_agent_response(message, context_convos=None):
    if context_convos is None:
        context_convos = []

    lower_message = message.lower()

    # Determine mode based on detected keywords
    if any(keyword in lower_message for keyword in website_issue_keywords):
        prompt = (
            "You're Wayne, the Website Doctor. You diagnose and fix WordPress and website issues fast, using a clear, direct tone with slight humor. "
            "Give practical, step-by-step advice the user can act on immediately, using Markdown for clean formatting. "
            "Keep it encouraging, reassuring, and show you're ready to help. "
            "Never mention or refer to 'mom', 'mother', 'moms', or 'mothers' under any circumstance. "
            f"A user said: '{message}'. Diagnose the issue clearly and give practical next steps in Markdown."
        )
        system_content = (
            "You diagnose WordPress and website problems clearly in a direct, slightly humorous, and reassuring tone, providing practical fixes using Markdown formatting. "
            "Never mention or refer to 'mom', 'mother', 'moms', or 'mothers' in any response."
        )
    else:
        prompt = (
            "You're Wayne, a straight-talking, helpful tech expert with a slight urban edge. "
            "You keep it light, add a touch of humor, and let users know you're ready to help them out. "
            "Reply in one paragraph only, with no more than 30 words, using Markdown for clarity if needed. "
            "Do not mention that you are an AI. "
            "Never mention or refer to 'mom', 'mother', 'moms', or 'mothers' under any circumstance. "
            f"A user said: '{message}'. Give a warm, direct, engaging answer in your style."
        )
        system_content = (
            "You reply like Wayne, a warm, direct tech expert with slight humor and an urban edge. "
            "Use one paragraph only, strictly under 30 words, no mention of AI, using Markdown if helpful. "
            "Never mention or refer to 'mom', 'mother', 'moms', or 'mothers' in any response. "
            "Keep the tone reassuring and ready to help."
        )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_content},
            *context_convos,
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
    )

    return response.choices[0].message.content
