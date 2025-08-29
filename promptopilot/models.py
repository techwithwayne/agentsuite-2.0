from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator


class AdPrompt(models.Model):
    """
    Stores each prompt submitted by a user for the Ad Builder tool.
    """

    TOOL_CHOICES = [
        ("ad_builder", "Ad Builder"),
        # Future tools can be added here
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ad_prompts")
    tool = models.CharField(max_length=50, choices=TOOL_CHOICES, default="ad_builder", db_index=True)
    prompt_text = models.TextField(
        help_text="The prompt submitted to the AI.",
        validators=[MaxLengthValidator(2000)]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.tool} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["tool"]),
        ]
        ordering = ["-created_at"]


class AdResult(models.Model):
    """
    Stores the AI-generated result from the prompt.
    """

    prompt = models.OneToOneField(AdPrompt, on_delete=models.CASCADE, related_name="result")
    output_text = models.TextField(help_text="The AI-generated content.")
    model_used = models.CharField(max_length=50, default="gpt-4o", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Output for {self.prompt.tool} at {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["model_used"]),
        ]
        ordering = ["-created_at"]


class PromptHistory(models.Model):
    """
    General-purpose prompt + output log for history display.
    Works with anonymous or identified users.
    """

    user_id = models.CharField(max_length=100)  # Use session ID or user ID
    product_name = models.CharField(max_length=255, db_index=True)
    audience = models.TextField()
    tone = models.CharField(max_length=100)
    model_used = models.CharField(max_length=50, db_index=True)
    result = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} - {self.product_name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["product_name"]),
            models.Index(fields=["tone"]),
        ]
        ordering = ["-created_at"]
