from django.db import models
from .assessment_session import AssessmentSession  # Link back to session


class CognitiveAbility(models.Model):
    """
    Stores cognitive ability results for a given assessment session.
    We’re breaking it down into multiple measurable components.
    """

    # Tie cognitive results to a specific session
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="cognitive_scores"  # lets us call session.cognitive_scores.all()
    )

    # Example components of cognitive testing.
    reasoning = models.PositiveSmallIntegerField(default=0, help_text="Logical reasoning score")
    memory = models.PositiveSmallIntegerField(default=0, help_text="Memory retention score")
    problem_solving = models.PositiveSmallIntegerField(default=0, help_text="Problem solving ability")
    attention = models.PositiveSmallIntegerField(default=0, help_text="Attention and focus score")

    # Optional notes field for evaluator or AI auto-feedback
    notes = models.TextField(blank=True)

    # Timestamp for when this record was created
    created_at = models.DateTimeField(auto_now_add=True)

    def overall_score(self):
        """
        Calculates the average cognitive ability score.
        Example: (reasoning + memory + problem_solving + attention) / 4
        """
        values = [self.reasoning, self.memory, self.problem_solving, self.attention]
        return sum(values) / len(values) if values else 0

    def __str__(self):
        """
        Example output in shell/admin:
        "Cognitive Scores for Session #1 (Avg: 82.5)"
        """
        return f"Cognitive Scores for Session #{self.session.id} (Avg: {self.overall_score()})"
