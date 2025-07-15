from django.db import models

class WebsiteScan(models.Model):
    url = models.URLField()
    scanned_at = models.DateTimeField(auto_now_add=True)
    issues_found = models.TextField()
    recommendations = models.TextField()

    def __str__(self):
        return f"{self.url} scanned on {self.scanned_at}"