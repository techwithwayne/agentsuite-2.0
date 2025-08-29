from django.core.management.base import BaseCommand, CommandParser
from django.conf import settings
from django.core.mail import send_mail

class Command(BaseCommand):
    help = "Send a test email using the current EMAIL_BACKEND / Mailgun config."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("to_email", help="Destination email address to send the test message to.")

    def handle(self, *args, **options):
        to_email = options["to_email"]
        subject = "Personal Mentor • Test Email"
        message = (
            "This is a test email from the Personal Mentor app on PythonAnywhere.\n"
            f"Backend: {settings.EMAIL_BACKEND}\n"
            f"From: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')}\n"
        )
        self.stdout.write(self.style.NOTICE(f"EMAIL_BACKEND = {settings.EMAIL_BACKEND}"))
        self.stdout.write(self.style.NOTICE(f"DEFAULT_FROM_EMAIL = {getattr(settings, 'DEFAULT_FROM_EMAIL', '')}"))
        try:
            sent = send_mail(subject, message, getattr(settings, "DEFAULT_FROM_EMAIL", None), [to_email], fail_silently=False)
            if sent == 1:
                self.stdout.write(self.style.SUCCESS(f"OK • Sent to {to_email}"))
            else:
                self.stdout.write(self.style.WARNING(f"Partial/unknown result • send_mail returned {sent}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"FAILED • {e}"))
            raise
