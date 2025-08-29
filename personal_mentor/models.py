from __future__ import annotations
import uuid
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def _six_digit_code() -> str:
    # 6-digit numeric code
    return f"{secrets.randbelow(1_000_000):06d}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="mentor_profile")
    verification_code = models.CharField(max_length=6, blank=True, default="")
    code_sent_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_resend_at = models.DateTimeField(null=True, blank=True)

    # app bookkeeping
    created_at = models.DateTimeField(auto_now_add=True)

    CODE_TTL = timedelta(minutes=20)
    RESEND_COOLDOWN = timedelta(minutes=2)

    def needs_verification(self) -> bool:
        return self.verified_at is None

    def code_valid(self, code: str) -> bool:
        if not self.verification_code or not self.code_sent_at:
            return False
        if timezone.now() > (self.code_sent_at + self.CODE_TTL):
            return False
        return code == self.verification_code

    def issue_code(self) -> str:
        code = _six_digit_code()
        self.verification_code = code
        self.code_sent_at = timezone.now()
        self.save(update_fields=["verification_code", "code_sent_at"])
        return code

    def can_resend(self) -> bool:
        if self.last_resend_at is None:
            return True
        return timezone.now() >= (self.last_resend_at + self.RESEND_COOLDOWN)

    def mark_resend(self) -> None:
        self.last_resend_at = timezone.now()
        self.save(update_fields=["last_resend_at"])
