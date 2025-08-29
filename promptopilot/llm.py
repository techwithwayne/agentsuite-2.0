# promptopilot/llm.py

import os
import openai
import anthropic

# Create a client for each provider
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
claude_client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

def get_llm_response(prompt: str, model: str = "gpt-4o") -> str:
    """
    Generate an AI response using GPT-4o or Claude, depending on the selected model.
    Uses updated OpenAI SDK format (>=1.0).
    """
    try:
        if model == "gpt-4o":
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1024
            )
            return response.choices[0].message.content.strip()

        elif model == "claude":
            response = claude_client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1024,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        else:
            return "Unsupported model requested. Try 'gpt-4o' or 'claude'."

    except Exception as e:
        return f"Error from {model}: {str(e)}"
