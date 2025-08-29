from django.db import models

class StoredArticle(models.Model):
    # WordPress-side identity
    wp_post_id = models.IntegerField(null=True, blank=True, db_index=True)
    wp_permalink = models.URLField(null=True, blank=True)

    # Inputs
    subject = models.CharField(max_length=255)
    genre = models.CharField(max_length=120, blank=True)
    tone = models.CharField(max_length=120, blank=True)

    # Output (final approved)
    title = models.CharField(max_length=255)
    html = models.TextField()
    summary = models.TextField(blank=True)

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    stored_at = models.DateTimeField(auto_now=True)
    source = models.CharField(max_length=64, default="wordpress")  # future multi-source
    billing_plan = models.CharField(max_length=64, blank=True)      # future payments

    def __str__(self):
        return f"[{self.wp_post_id}] {self.title}" if self.wp_post_id else self.title
