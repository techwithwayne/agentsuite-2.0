# website_analyzer/fetcher.py
import time
import requests
from .validators import validate_target_url

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 WebDoctorBot/1.0 (+https://techwithwayne.com/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

def fetch_url(user_input_url: str, timeout=15, tries=3):
    """
    Robust fetch for arbitrary user-supplied URLs:
    - Validates & normalizes URL (HTTPS, public IPs only)
    - Browser-like headers
    - Redirects allowed
    - Gentle retry for 403/429 with minor UA jitter
    """
    url = validate_target_url(user_input_url)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    last_err = None
    for i in range(tries):
        try:
            resp = session.get(url, allow_redirects=True, timeout=timeout)
            # Handle common WAF blocks
            if resp.status_code in (401, 403, 409, 429):
                session.headers["User-Agent"] = DEFAULT_HEADERS["User-Agent"] + f" r{i+1}"
                last_err = Exception(f"HTTP {resp.status_code}")
                time.sleep(1.0 + 0.5 * i)
                continue

            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")

            return {
                "ok": True,
                "requested_url": user_input_url,
                "final_url": resp.url,
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "text": resp.text,
            }

        except requests.RequestException as e:
            last_err = e
            time.sleep(0.5 + 0.5 * i)

    return {
        "ok": False,
        "requested_url": user_input_url,
        "error": str(last_err) if last_err else "Unknown fetch error",
    }
