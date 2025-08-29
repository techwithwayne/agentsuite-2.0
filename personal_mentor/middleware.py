from django.http import JsonResponse

class MentorAccessMiddleware:
    """
    Blocks access to /personal-mentor/api/* unless the session has mentor_verified True
    or the authenticated user's profile is verified. Explicitly exempts the health
    endpoint so frontends can ping it before auth.
    """
    API_PREFIXES = ("/personal-mentor/api/",)
    EXEMPT_PATHS = {
        "/personal-mentor/api/health/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or "")
        # Exempt explicit health path
        if path in self.EXEMPT_PATHS:
            return self.get_response(request)

        if path.startswith(self.API_PREFIXES):
            is_verified = bool(request.session.get("mentor_verified"))

            if not is_verified:
                user = getattr(request, "user", None)
                if user and user.is_authenticated:
                    prof = getattr(user, "mentor_profile", None)
                    if prof and getattr(prof, "verified_at", None):
                        request.session["mentor_verified"] = True
                        is_verified = True

            if not is_verified:
                return JsonResponse(
                    {"ok": False, "error": "Not verified. Please register and confirm email."},
                    status=403,
                )

        return self.get_response(request)
