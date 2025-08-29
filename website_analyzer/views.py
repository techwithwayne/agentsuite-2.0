from django.shortcuts import render
from django.http import HttpResponse
from .forms import URLScanForm
from .models import WebsiteScan
from .openai_client import get_openai_client

import os
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# website_analyzer/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from .fetcher import fetch_url

def _get_url_from_request(request):
    if request.method == "GET":
        return request.GET.get("url")
    # POST: accept JSON { "url": "..." } or form field
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body or b"{}")
            return (data.get("url") or "").strip()
        except json.JSONDecodeError:
            return None
    return (request.POST.get("url") or "").strip()

@require_http_methods(["GET", "POST"])
def analyze_api(request):
    """
    Public endpoint: accepts any website URL; never hardcoded.
    Returns minimal diagnostics and leaves HTML for downstream analyzers.
    """
    url = _get_url_from_request(request)
    if not url:
        return HttpResponseBadRequest("Missing 'url' parameter")

    result = fetch_url(url)
    if result.get("ok"):
        # keep payload tight; don’t dump entire HTML here
        headers = result.get("headers", {})
        return JsonResponse({
            "ok": True,
            "requested_url": result["requested_url"],
            "final_url": result["final_url"],
            "status": result["status"],
            "content_type": headers.get("Content-Type"),
            "server": headers.get("Server"),
        })

    # Don’t call this “site down” — it’s usually access-blocked
    return JsonResponse({
        "ok": False,
        "requested_url": result.get("requested_url", url),
        "message": ("We reached the server but access was blocked or restricted "
                    "(e.g., 403/401/429). Some sites block non-browser requests."),
        "detail": result.get("error"),
    }, status=200)

@require_http_methods(["GET"])
def fetch_diagnostics(request):
    """
    Developer-only helper: echoes what the server can fetch.
    """
    url = _get_url_from_request(request) or "https://example.com"
    result = fetch_url(url)
    if result.get("ok"):
        headers = result.get("headers", {})
        return JsonResponse({
            "ok": True,
            "requested_url": result["requested_url"],
            "final_url": result["final_url"],
            "status": result["status"],
            "content_type": headers.get("Content-Type"),
            "server": headers.get("Server"),
        })
    return JsonResponse({"ok": False, "requested_url": url, "error": result.get("error")}, status=200)


# ---------- Utilities ----------

def generate_layout_suggestions(title, headings, url):
    """
    Attempts to fetch JSON layout suggestions from OpenAI.
    If OpenAI is not configured or returns non‑JSON, we fail gracefully.
    """
    # Only attempt if we have a key
    if not os.getenv("OPENAI_API_KEY"):
        return []

    try:
        client = get_openai_client()
    except Exception as e:
        # No key or misconfig: just skip suggestions
        print(f"[OpenAI disabled]: {e}")
        return []

    headings_text = "\n".join(
        [f"{tag.upper()}: {text}" for tag, texts in headings.items() for text in texts]
    )

    prompt = (
        "You are Wayne, an expert website developer helping clients improve their websites. "
        "Given the following site details, suggest a clean, modern website layout structure suitable for this site, "
        "including recommended sections, hero layout, and CTA placement.\n\n"
        "For each suggestion, return structured JSON only with:\n"
        "{\n"
        '"what": "What to implement",\n'
        '"why": "Why it matters",\n'
        '"example_link": "A placeholder link"\n'
        "},\n\n"
        "Return a JSON array only, no commentary or markdown.\n\n"
        f"Site URL: {url}\n"
        f"Title: {title}\n"
        f"Headings:\n{headings_text}\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You return only valid JSON with layout suggestions structured exactly as instructed."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        json_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[OpenAI error]: {e}")
        return []

    try:
        # If any stray text, grab the JSON array
        json_extracted = re.search(r"\[.*\]", json_text, re.DOTALL).group(0)
        layout_suggestions = json.loads(json_extracted)
    except Exception as e:
        print(f"[Layout Suggestion Parsing Error]: {e}")
        print(f"[Raw GPT Output]: {json_text}")
        layout_suggestions = []

    # Add example links heuristically
    for s in layout_suggestions:
        what = s.get("what", "").lower()
        if any(k in what for k in ["header", "nav", "sticky"]):
            s["example_link"] = "https://dribbble.com/search/website%20header"
        elif "hero" in what:
            s["example_link"] = "https://dribbble.com/search/website%20hero"
        elif "about" in what:
            s["example_link"] = "https://dribbble.com/search/website%20about"
        elif any(k in what for k in ["feature", "services", "product"]):
            s["example_link"] = "https://dribbble.com/search/website%20features"
        elif "event" in what:
            s["example_link"] = "https://dribbble.com/search/website%20event"
        elif "cta" in what or "call-to-action" in what:
            s["example_link"] = "https://dribbble.com/search/website%20cta"
        elif "testimonial" in what:
            s["example_link"] = "https://dribbble.com/search/website%20testimonial"
        elif "contact" in what:
            s["example_link"] = "https://dribbble.com/search/website%20contact"
        elif "footer" in what:
            s["example_link"] = "https://dribbble.com/search/website%20footer"
        else:
            s["example_link"] = "https://dribbble.com/search/modern%20website"

    return layout_suggestions


def scan_website(url):
    general_issues = []
    recommendations = []
    missing_alt_images = []
    broken_links = []
    headings_found = {f"h{i}": [] for i in range(1, 7)}

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Title
        title_tag = soup.find("title")
        if not title_tag:
            general_issues.append("Missing <title> tag.")
            recommendations.append({
                "recommendation": "Add a clear, keyword-rich <title> tag.",
                "why": "Search engines use your title to determine page content, influencing rankings and CTR.",
                "urgency": "High",
            })
        elif len(title_tag.text.strip()) < 10:
            general_issues.append(f"Title too short: '{title_tag.text.strip()}'.")
            recommendations.append({
                "recommendation": "Expand your <title> tag with relevant keywords.",
                "why": "A short title may not provide enough context for search engines.",
                "urgency": "High",
            })

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc:
            general_issues.append("Missing meta description.")
            recommendations.append({
                "recommendation": "Add a clear, keyword-focused meta description.",
                "why": "Helps search engines and users understand your page and can improve CTR.",
                "urgency": "Medium",
            })
        elif len(meta_desc.get("content", "").strip()) < 50:
            general_issues.append("Meta description too short.")
            recommendations.append({
                "recommendation": "Expand your meta description to ~150–160 characters.",
                "why": "Short descriptions don’t effectively summarize your page.",
                "urgency": "Medium",
            })

        # Headings
        for i in range(1, 7):
            for t in soup.find_all(f"h{i}"):
                text = t.get_text(strip=True)
                if text:
                    headings_found[f"h{i}"].append(text)

        h1_count = len(headings_found["h1"])
        if h1_count == 0:
            general_issues.append("No <h1> tag found.")
            recommendations.append({
                "recommendation": "Add a descriptive <h1> tag.",
                "why": "<h1> helps users and search engines understand the primary topic.",
                "urgency": "High",
            })
        elif h1_count > 1:
            general_issues.append(f"Multiple <h1> tags found: {h1_count}.")
            recommendations.append({
                "recommendation": "Use only one <h1> per page.",
                "why": "Multiple <h1> tags can dilute topical focus.",
                "urgency": "High",
            })

        # Images missing alt
        for img in soup.find_all("img"):
            if not img.get("alt"):
                src = img.get("src") or img.get("data-src") or "Unknown src"
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = urljoin(url, src)
                missing_alt_images.append(src)
        if missing_alt_images:
            general_issues.append(f"{len(missing_alt_images)} images missing alt attributes.")
            recommendations.append({
                "recommendation": "Add descriptive alt text to all images.",
                "why": "Improves accessibility and helps search engines understand images.",
                "urgency": "Medium",
            })

        # Broken links (lightweight HEAD check)
        links = soup.find_all("a", href=True)
        base_url = "{0.scheme}://{0.netloc}".format(urlparse(url))
        checked = set()
        for a in links:
            href = a["href"]
            if href.startswith(("#", "mailto:", "tel:")):
                continue
            full = (
                urljoin(base_url, href) if href.startswith("/") else
                (href if href.startswith("http") else urljoin(url, href))
            )
            if full in checked:
                continue
            checked.add(full)
            try:
                r = requests.head(full, allow_redirects=True, timeout=5)
                if r.status_code >= 400:
                    broken_links.append(full)
            except Exception:
                broken_links.append(full)
        if broken_links:
            general_issues.append(f"{len(broken_links)} broken links found.")
            recommendations.append({
                "recommendation": "Fix or remove broken links.",
                "why": "Broken links harm UX and can impact SEO.",
                "urgency": "High",
            })

        # Baseline design advice
        recommendations.extend([
            {
                "recommendation": "Use a clean, uncluttered layout with clear section separation.",
                "why": "Helps visitors find what they need quickly.",
                "urgency": "Medium",
            },
            {
                "recommendation": "Verify mobile responsiveness across devices.",
                "why": "Over half of traffic is mobile; poor UX causes drop‑offs.",
                "urgency": "High",
            },
            {
                "recommendation": "Keep fonts and colors consistent.",
                "why": "Consistency builds brand trust and looks professional.",
                "urgency": "Medium",
            },
            {
                "recommendation": "Add clear calls‑to‑action (CTAs).",
                "why": "Guides users to the next step and boosts conversions.",
                "urgency": "High",
            },
        ])

    except Exception as e:
        general_issues.append(f"Error accessing site: {e}")
        recommendations.append({
            "recommendation": "Ensure your site is live and accessible.",
            "why": "If the site is down, visitors and crawlers can’t reach it.",
            "urgency": "High",
        })

    return {
        "general_issues": general_issues,
        "recommendations": recommendations,
        "missing_alt_images": missing_alt_images[:6],
        "headings_found": headings_found,
        "broken_links": broken_links,
    }

# ---------- Views ----------

def home(request):
    if request.method == "POST":
        form = URLScanForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            scan_data = scan_website(url)

            # Extract a title for the page (non‑fatal)
            title = ""
            try:
                r = requests.get(url, timeout=12)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                t = soup.find("title")
                title = t.text.strip() if t else ""
            except Exception:
                pass

            layout_suggestions = generate_layout_suggestions(title, scan_data["headings_found"], url)

            # Save a summary row
            try:
                WebsiteScan.objects.create(
                    url=url,
                    issues_found="\n".join(scan_data["general_issues"]),
                    recommendations="\n".join([rec["recommendation"] for rec in scan_data["recommendations"]]),
                )
            except Exception as e:
                print(f"[DB save skipped]: {e}")

            return render(
                request,
                "website_analyzer/results.html",
                {
                    "url": url,
                    "page_title": title,
                    **scan_data,
                    "layout_suggestions": layout_suggestions,
                },
            )
    else:
        form = URLScanForm()

    return render(request, "website_analyzer/home.html", {"form": form})
