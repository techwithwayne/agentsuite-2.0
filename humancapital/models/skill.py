from django.db import models
from .assessment_session import AssessmentSession  # Link skills to a session


class Skill(models.Model):
    """
    Represents a single skill entry that was assessed for a given session.
    Each skill belongs to an AssessmentSession.
    """

    # Link each skill rating back to the specific session.
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="skills"  # lets us call session.skills.all()
    )

    # Category of skill (e.g., "Programming", "Project Management", "Data Analysis").
    category = models.CharField(max_length=100)

    # Specific name of the skill (e.g., "Python", "Agile Scrum", "SQL").
    name = models.CharField(max_length=100)

    # Proficiency rating: Likert scale (1 = beginner, 5 = expert).
    rating = models.PositiveSmallIntegerField(default=1)

    # Optional weight (allows some skills to count more toward overall score).
    weight = models.FloatField(default=1.0)

    # Timestamp when this skill record was created.
    created_at = models.DateTimeField(auto_now_add=True)

    def weighted_score(self):
        """
        Returns the weighted score for this skill.
        Example: rating (4) * weight (1.5) = 6.0
        """
        return self.rating * self.weight

    def __str__(self):
        """
        String representation shown in Django admin or shell.
        Example: "Python (Rating: 4)"
        """
        return f"{self.name} (Rating: {self.rating})"
