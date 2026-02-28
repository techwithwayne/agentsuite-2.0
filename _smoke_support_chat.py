import os, json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "agentsuite.settings")

import django
django.setup()

from django.test import Client

secret = os.environ.get("PPA_WP_SHARED_SECRET", "")
c = Client(HTTP_X_PPA_SHARED_SECRET=secret)

resp = c.post(
    "/postpress-ai/support/chat/",
    data=json.dumps({"message": "hi"}),
    content_type="application/json",
    secure=True,  # IMPORTANT: prevents HTTP->HTTPS redirect in dev test client
)

print("STATUS", resp.status_code)
print("LOCATION", resp.headers.get("Location", ""))
print(resp.content.decode("utf-8"))
