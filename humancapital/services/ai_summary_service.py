# CHANGE LOG
# Aug 29, 2025 — Harden AI summary for PythonAnywhere; env-gated; never raises; returns fallback.
# Notes:
# - Set HC_DISABLE_AI=0 to enable AI (default disabled).
# - Handles missing OPENAI_API_KEY / SDK / network without raising.

import os
from typing import Optional

# CHANGED: Try-import settings for PA shell/offline contexts.
try:
    from django.conf import settings  # type: ignore  # CHANGED
except Exception:  # CHANGED
    settings = None  # type: ignore  # CHANGED

# CHANGED: Env/setting flags — default DISABLED for safety on PA
ENV_DISABLE = os.environ.get("HC_DISABLE_AI", "1") not in ("0", "false", "False")  # CHANGED
SETT_DISABLE = bool(getattr(settings, "HUMANCAPITAL_DISABLE_AI", False)) if settings else False  # CHANGED
DISABLED = ENV_DISABLE or SETT_DISABLE  # CHANGED

def _openai_client():  # CHANGED
    api_key = os.environ.get("OPENAI_API_KEY") or (getattr(settings, "OPENAI_API_KEY", None) if settings else None)  # CHANGED
    if not api_key:
        return None  # CHANGED
    try:
        from openai import OpenAI  # type: ignore  # CHANGED
        return OpenAI(api_key=api_key)  # CHANGED
    except Exception:
        return None  # CHANGED

def generate_ai_summary(session) -> str:  # CHANGED
    fallback = (
        "AI summary is currently disabled or unavailable.\n"
        f"Session ID: {getattr(session, 'id', 'n/a')}."
    )  # CHANGED

    if DISABLED:  # CHANGED
        return fallback  # CHANGED

    client = _openai_client()  # CHANGED
    if client is None:  # CHANGED
        return fallback  # CHANGED

    try:
        # CHANGED: be defensive on related sets
        up   = getattr(session, "user_profile", None)
        sk   = getattr(session, "skill_set", None)
        cog  = getattr(session, "cognitiveability_set", None)
        pers = getattr(session, "personality_set", None)
        beh  = getattr(session, "behavior_set", None)
        mot  = getattr(session, "motivation_set", None)

        prompt = "Create a concise human-capital snapshot.\n"  # CHANGED
        if up:   prompt += f"Role: {getattr(up, 'current_role', '')}\n"
        if sk:   prompt += f"Skills: {sk.count()}\n"
        if cog:  prompt += f"Cognitive: {cog.count()}\n"
        if pers: prompt += f"Personality: {pers.count()}\n"
        if beh:  prompt += f"Behavior: {beh.count()}\n"
        if mot:  prompt += f"Motivation: {mot.count()}\n"

        resp = client.chat.completions.create(  # CHANGED
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise HR analyst."},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.3,
            max_tokens=250,
        )
        text = (resp.choices[0].message.content or "").strip()  # CHANGED
        return text or fallback  # CHANGED
    except Exception:
        return fallback  # CHANGED
