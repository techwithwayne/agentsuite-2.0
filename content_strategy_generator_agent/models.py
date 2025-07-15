from django.db import models

class StrategyRequest(models.Model):
    niche = models.CharField(max_length=255)
    goals = models.TextField()
    tone = models.CharField(max_length=100)
    result = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.niche} - {self.tone} ({self.created_at.strftime('%Y-%m-%d')})"
