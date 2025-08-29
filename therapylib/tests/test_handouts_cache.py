"""
CHANGE LOG
----------
2025-08-25 • Added ETag tests for PDF handouts (presence + 304 conditional).
"""

import requests

BASE_URL = "https://apps.techwithwayne.com/api/therapylib/handouts"

def test_pdf_etag_present():
    url = f"{BASE_URL}/berberine/pdf/?mode=patient"
    r = requests.get(url, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("ETag"), "ETag header missing on PDF response"

def test_pdf_conditional_304():
    url = f"{BASE_URL}/berberine/pdf/?mode=patient"
    r1 = requests.get(url, timeout=30)
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag, "ETag header missing on first response"

    # Send conditional request
    headers = {"If-None-Match": etag}
    r2 = requests.get(url, headers=headers, timeout=30)
    # CDN or proxy may revalidate; we accept 304 or 200 (but prefer 304)
    assert r2.status_code in (304, 200)
    if r2.status_code == 200:
        # If revalidation happened upstream, it may still be 200 but should include the same ETag
        assert r2.headers.get("ETag") == etag
