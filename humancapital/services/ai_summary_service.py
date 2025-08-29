"""
CHANGE LOG:
- Updated OpenAI model to `gpt-4o` for compatibility on PythonAnywhere.
- Added DB persistence (stores AI summary in AssessmentSession).
- Improved logging and safe fallbacks (no 500 crashes).
"""

import logging
from django.conf import settings
from openai import OpenAI
from humancapital.models.assessment_session import AssessmentSession

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

def generate_ai_summary(session_id: int) -> str:
    """
    Generate an AI-powered summary for a given AssessmentSession.
    Stores the result in DB for later access.
    Returns safe fallback if API fails.
    """
    try:
        # Pull session object
        session = AssessmentSession.objects.get(id=session_id)

        # Build structured input text
        input_text = f"""
        Human Capital Assessment Summary
        --------------------------------
        Name: {session.user_profile.full_name if session.user_profile else "N/A"}

        Skills:
        {session.skills.values_list('name', flat=True)}

        Cognitive Abilities:
        {session.cognitive.values_list('ability', flat=True)}

        Personality (OCEAN):
        {session.personality.values_list('trait', flat=True)}

        Behaviors:
        {session.behavior.values_list('pattern', flat=True)}

        Motivations:
        {session.motivation.values_list('factor', flat=True)}
        """

        # OpenAI API call
        response = client.chat.completions.create(
            model="gpt-4o",  # CHANGED: supported model
            messages=[
                {
                    "role": "system",
                    "content": "You are an HR expert providing clear and friendly assessment summaries."
                },
                {
                    "role": "user",
                    "content": input_text
                }
            ],
            max_tokens=500,
            temperature=0.7,
        )

        # Extract text
        ai_text = response.choices[0].message.content.strip()

        # Save into DB (new field required)
        session.ai_summary = ai_text
        session.save(update_fields=["ai_summary"])

        return ai_text

    except Exception as e:
        logger.error("AI summary generation failed", exc_info=True)
        return "AI summary could not be generated at this time. Please review the entered data."
