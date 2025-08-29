from django.db import models
from .assessment_session import AssessmentSession


class Response(models.Model):
    """
    Stores individual responses to assessment questions.
    This acts as the atomic 'event log' for the assessment system.
    """

    # Each response belongs to a session
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    # Type of question (skill, cognitive, personality, behavior, motivation)
    question_type = models.CharField(
        max_length=50,
        help_text="Which section this question belongs to (e.g., skill, personality, etc.)"
    )

    # The actual question text (stored for traceability, even if questions change later)
    question_text = models.TextField()

    # The answer given by the user (text, Likert value, multiple choice label, etc.)
    answer_text = models.TextField()

    # Numeric value (if applicable — e.g., Likert scale 1–5, or score)
    answer_value = models.FloatField(null=True, blank=True)

    # How long the user took to answer (in seconds)
    response_time = models.FloatField(null=True, blank=True)

    # Timestamp when response was recorded
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """
        Example string:
        "Response: [skill] Python Proficiency = 4"
        """
        val = f" = {self.answer_value}" if self.answer_value is not None else ""
        return f"Response: [{self.question_type}] {self.question_text}{val}"
