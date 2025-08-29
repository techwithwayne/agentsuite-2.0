from django.db import models
from .assessment_session import AssessmentSession  # Every behavior record belongs to a session


class Behavior(models.Model):
    """
    Captures behavioral style indicators for a given session.
    This includes how a person communicates, makes decisions, and collaborates.
    """

    # Link back to session
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="behavior_profiles"
    )

    # Key behavioral indicators — stored as scores (0–100 scale for flexibility).
    communication = models.PositiveSmallIntegerField(default=0, help_text="Clarity and style of communication")
    decision_making = models.PositiveSmallIntegerField(default=0, help_text="Speed and confidence in decisions")
    leadership = models.PositiveSmallIntegerField(default=0, help_text="Leadership vs. support orientation")
    collaboration = models.PositiveSmallIntegerField(default=0, help_text="Ability to collaborate effectively")
    conflict_handling = models.PositiveSmallIntegerField(default=0, help_text="How the person manages conflict")

    # Optional evaluator/AI notes
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def average_score(self):
        """
        Returns the average behavioral score across all indicators.
        """
        values = [
            self.communication,
            self.decision_making,
            self.leadership,
            self.collaboration,
            self.conflict_handling,
        ]
        return sum(values) / len(values) if values else 0

    def strongest_trait(self):
        """
        Returns the behavioral indicator with the highest score.
        Example: 'Collaboration' if collaboration is the highest value.
        """
        traits = {
            "Communication": self.communication,
            "Decision Making": self.decision_making,
            "Leadership": self.leadership,
            "Collaboration": self.collaboration,
            "Conflict Handling": self.conflict_handling,
        }
        return max(traits, key=traits.get)

    def __str__(self):
        """
        Example output in shell/admin:
        "Behavior Profile for Session #1 (Strongest: Collaboration)"
        """
        return f"Behavior Profile for Session #{self.session.id} (Strongest: {self.strongest_trait()})"
