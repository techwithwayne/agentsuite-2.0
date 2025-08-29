from django.db import models
from .assessment_session import AssessmentSession


class Scorecard(models.Model):
    """
    Stores aggregated scores for an assessment session.
    This provides a quick overview of the candidate's human capital profile.
    """

    # Link back to the session this scorecard belongs to
    session = models.OneToOneField(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="scorecard"
    )

    # Component scores (0–100 scale)
    skill_index = models.FloatField(default=0, help_text="Overall technical/professional skill score")
    cognitive_index = models.FloatField(default=0, help_text="Cognitive ability score")
    personality_index = models.FloatField(default=0, help_text="Personality balance score")
    behavior_index = models.FloatField(default=0, help_text="Behavioral style score")
    motivation_index = models.FloatField(default=0, help_text="Motivation/drive score")

    # AI/Evaluator summary (executive-level narrative)
    summary = models.TextField(blank=True)

    # Timestamp when scorecard was generated
    created_at = models.DateTimeField(auto_now_add=True)

    def overall_index(self):
        """
        Returns the average of all component indices.
        Example: (skill + cognitive + personality + behavior + motivation) / 5
        """
        values = [
            self.skill_index,
            self.cognitive_index,
            self.personality_index,
            self.behavior_index,
            self.motivation_index,
        ]
        return sum(values) / len(values) if values else 0

    def __str__(self):
        """
        Example output:
        "Scorecard for Session #1 (Overall: 78.2)"
        """
        return f"Scorecard for Session #{self.session.id} (Overall: {self.overall_index():.1f})"
