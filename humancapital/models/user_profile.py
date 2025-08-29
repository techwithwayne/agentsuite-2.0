from django.db import models

class UserProfile(models.Model):
    """Basic demographic and job info for assessment participants."""

    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    job_title = models.CharField(max_length=255, blank=True)
    industry = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # CHANGED: audit trail
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name} ({self.email})"
