# agentsuite/middleware.py
from django.utils.deprecation import MiddlewareMixin

ALLOWED_IFRAME_PARENTS = [
    "https://showcase.techwithwayne.com",
    "https://promptopilot.com",
    "https://tools.promptopilot.com",
    "https://apps.techwithwayne.com",  # optional: lets you embed app into itself/subpages
]

class FrameAncestorMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Remove any existing X-Frame-Options header (some stacks set SAMEORIGIN by default)
        if "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]

        # Set modern, allowlisted embed policy
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors " + " ".join(ALLOWED_IFRAME_PARENTS)
        )

        # Optional: explicitly allow all frames (modern browsers use CSP above anyway)
        # response.headers["X-Frame-Options"] = "ALLOWALL"

        return response
