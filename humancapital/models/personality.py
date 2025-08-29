from django.db import models
from .assessment_session import AssessmentSession  # Every personality profile belongs to a session


class Personality(models.Model):
    """
    Stores Big Five (OCEAN) personality trait results for a given assessment session.
    Each field is stored as a score (0–100) for easier scaling and analysis.
    """

    # Tie the personality profile to the session
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="personality_profiles"
    )

    # Big Five Traits
    openness = models.PositiveSmallIntegerField(default=0, help_text="Openness to new experiences")
    conscientiousness = models.PositiveSmallIntegerField(default=0, help_text="Level of organization and dependability")
    extraversion = models.PositiveSmallIntegerField(default=0, help_text="Sociability and energy orientation")
    agreeableness = models.PositiveSmallIntegerField(default=0, help_text="Compassion and cooperativeness")
    neuroticism = models.PositiveSmallIntegerField(default=0, help_text="Tendency toward emotional instability")

    # Optional notes (AI or evaluator insights)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def overall_balance(self):
        """
        Returns a dictionary of trait scores.
        Useful for visualizing on a radar/spider chart.
        """
        return {
            "O": self.openness,
            "C": self.conscientiousness,
            "E": self.extraversion,
            "A": self.agreeableness,
            "N": self.neuroticism,
        }

    def dominant_trait(self):
        """
        Returns the trait with the highest score.
        Example: 'Extraversion' if extraversion > all others.
        """
        traits = {
            "Openness": self.openness,
            "Conscientiousness": self.conscientiousness,
            "Extraversion": self.extraversion,
            "Agreeableness": self.agreeableness,
            "Neuroticism": self.neuroticism,
        }
        return max(traits, key=traits.get)

    def __str__(self):
        """
        Example output in shell/admin:
        "Personality Profile for Session #1 (Dominant: Extraversion)"
        """
        return f"Personality Profile for Session #{self.session.id} (Dominant: {self.dominant_trait()})"
