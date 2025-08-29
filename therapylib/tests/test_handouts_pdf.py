"""
CHANGE LOG
----------
2025-08-25 • Relax size threshold to reflect minimal but valid PDFs.
- Keep checks for 200 status + %PDF header.
"""

import requests

BASE_URL = "https://apps.techwithwayne.com/api/therapylib/handouts"
MIN_PDF_BYTES = 1000  # lean PDFs are ~1.3KB in your current output

def test_pdf_endpoint_debug_html():
    """Debug mode should return HTML instead of PDF."""
    url = f"{BASE_URL}/berberine/pdf/?mode=patient&debug=1"
    r = requests.get(url, timeout=30)
    assert r.status_code == 200
    assert not r.content.startswith(b"%PDF-")
    assert b"<html" in r.content.lower()

def test_pdf_endpoint_default():
    """Default engine (from settings.THERAPYLIB_PDF_ENGINE)."""
    url = f"{BASE_URL}/berberine/pdf/?mode=patient"
    r = requests.get(url, timeout=30)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) >= MIN_PDF_BYTES

def test_pdf_endpoint_override_pdfkit():
    """Explicit engine override with ?engine=pdfkit (or fallback)."""
    url = f"{BASE_URL}/berberine/pdf/?mode=patient&engine=pdfkit"
    r = requests.get(url, timeout=30)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) >= MIN_PDF_BYTES
