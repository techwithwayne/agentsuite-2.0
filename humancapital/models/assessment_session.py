"""
CHANGE LOG:
- Added `ai_summary` field to store AI-generated assessment insights.
- Kept links to related models (skills, cognitive, personality, behavior, motivation).
"""

from django.db import models
from humancapital.models.user_profile import UserProfile


class AssessmentSession(models.Model):
    """
    Represents a single assessment journey for a user.
    Connects all assessment data together under one session.
    """

    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="sessions",
        null=True,
        blank=True
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # NEW FIELD: Stores AI summary text
    ai_summary = models.TextField(blank=True, null=True)  # CHANGED

    def __str__(self):
        return f"AssessmentSession #{self.id} for {self.user_profile if self.user_profile else 'Anonymous'}"

    class Meta:
        ordering = ["-started_at"]
