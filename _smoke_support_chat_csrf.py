import os, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "agentsuite.settings")

import django
django.setup()

from django.test import Client

# Enforce CSRF checks so this matches real browser behavior
c = Client(enforce_csrf_checks=True)

# OPTIONS preflight (force HTTPS so we don't get 301 before hitting the wrapper)
opt = c.options(
    "/postpress-ai/support/chat/",
    secure=True,
    **{
        "HTTP_ORIGIN": "https://example-wp-site.com",
        "HTTP_ACCESS_CONTROL_REQUEST_METHOD": "POST",
        "HTTP_ACCESS_CONTROL_REQUEST_HEADERS": "content-type",
    },
)
print("OPTIONS_STATUS", opt.status_code)
print("ALLOW_ORIGIN", opt.headers.get("Access-Control-Allow-Origin",""))
print("ALLOW_METHODS", opt.headers.get("Access-Control-Allow-Methods",""))
print("ALLOW_HEADERS", opt.headers.get("Access-Control-Allow-Headers",""))

# POST (force HTTPS; no CSRF token; wrapper must allow it)
post = c.post(
    "/postpress-ai/support/chat/",
    secure=True,
    data=json.dumps({"message":"hi"}),
    content_type="application/json",
    **{"HTTP_ORIGIN": "https://example-wp-site.com"},
)
print("POST_STATUS", post.status_code)
print(post.content.decode("utf-8"))
