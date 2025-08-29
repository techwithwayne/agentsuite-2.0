from django.db import models
from .assessment_session import AssessmentSession  # Each motivation record belongs to a session


class Motivation(models.Model):
    """
    Captures motivational drivers for a given assessment session.
    This helps understand what energizes or sustains a person at work.
    """

    # Link to the session this motivation profile belongs to
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="motivations"
    )

    # Motivational drivers (scored 0–100 for easy scaling/visualization)
    achievement = models.PositiveSmallIntegerField(default=0, help_text="Drive for success and results")
    stability = models.PositiveSmallIntegerField(default=0, help_text="Need for security and consistency")
    autonomy = models.PositiveSmallIntegerField(default=0, help_text="Desire for independence")
    recognition = models.PositiveSmallIntegerField(default=0, help_text="Need for praise and visibility")
    learning = models.PositiveSmallIntegerField(default=0, help_text="Motivation to learn and grow")

    # Optional notes (AI or evaluator commentary)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def strongest_driver(self):
        """
        Finds the motivation with the highest score.
        Example: 'Achievement' if achievement > all others.
        """
        drivers = {
            "Achievement": self.achievement,
            "Stability": self.stability,
            "Autonomy": self.autonomy,
            "Recognition": self.recognition,
            "Learning": self.learning,
        }
        return max(drivers, key=drivers.get)

    def __str__(self):
        """
        Example display in admin/shell:
        "Motivation Profile for Session #1 (Strongest: Learning)"
        """
        return f"Motivation Profile for Session #{self.session.id} (Strongest: {self.strongest_driver()})"
