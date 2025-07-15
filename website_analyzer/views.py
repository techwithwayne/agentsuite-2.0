from django.shortcuts import render
from .forms import URLScanForm
from .models import WebsiteScan
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from openai import OpenAI
import json
import re


def index(request):
    return HttpResponse("Hello from Website Analyzer!")
# Create your views here.

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_layout_suggestions(title, headings, url):
    headings_text = "\n".join([f"{tag.upper()}: {text}" for tag, texts in headings.items() for text in texts])

    prompt = (
        f"You are Wayne, an expert website developer helping clients improve their websites. "
        f"Given the following site details, suggest a clean, modern website layout structure suitable for this site, including recommended sections, hero layout, and CTA placement.\n\n"
        f"For each suggestion, return structured JSON only with:\n"
        f'{{\n'
        f'"what": "What to implement",\n'
        f'"why": "Why it matters",\n'
        f'"example_link": "A placeholder link"\n'
        f'}},\n\n'
        f"Return a JSON array only, no commentary or markdown.\n\n"
        f"Site URL: {url}\n"
        f"Title: {title}\n"
        f"Headings:\n{headings_text}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You return only valid JSON with layout suggestions structured exactly as instructed."},
            {"role": "user", "content": prompt}
        ]
    )

    json_text = response.choices[0].message.content.strip()

    try:
        json_extracted = re.search(r"\[.*\]", json_text, re.DOTALL).group(0)
        layout_suggestions = json.loads(json_extracted)
    except Exception as e:
        print(f"[Layout Suggestion Parsing Error]: {e}")
        print(f"[Raw GPT Output]: {json_text}")
        layout_suggestions = []

    # Deep research direct injection of real, high-quality inspiration links
    for suggestion in layout_suggestions:
        what = suggestion.get("what", "").lower()
        if "header" in what or "navigation" in what or "sticky" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20header"
        elif "hero" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20hero"
        elif "about" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20about"
        elif "feature" in what or "album" in what or "discography" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20album"
        elif "event" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20event"
        elif "cta" in what or "call-to-action" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20cta"
        elif "testimonial" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20testimonial"
        elif "contact" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20contact"
        elif "footer" in what:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website%20footer"
        else:
            suggestion["example_link"] = "https://dribbble.com/search/music%20website"


    return layout_suggestions

def scan_website(url):
    general_issues = []
    recommendations = []
    missing_alt_images = []
    broken_links = []
    headings_found = {f'h{i}': [] for i in range(1, 7)}

    try:
        response = requests.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Title check
        title_tag = soup.find('title')
        if not title_tag:
            general_issues.append("Missing <title> tag.")
            recommendations.append({
                "recommendation": "Add a clear, keyword-rich <title> tag.",
                "why": "Search engines use your title to determine page content, influencing your search rankings and click-through rates.",
                "urgency": "High"
            })
        elif len(title_tag.text.strip()) < 10:
            general_issues.append(f"Title too short: '{title_tag.text.strip()}'.")
            recommendations.append({
                "recommendation": "Expand your <title> tag with relevant keywords.",
                "why": "A short title may not give enough context to search engines, reducing your page's chances to rank well.",
                "urgency": "High"
            })

        # Meta description check
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc:
            general_issues.append("Missing meta description.")
            recommendations.append({
                "recommendation": "Add a clear, keyword-focused meta description.",
                "why": "Meta descriptions help search engines and users understand your page and can improve click-through rates.",
                "urgency": "Medium"
            })
        elif len(meta_desc.get('content', '').strip()) < 50:
            general_issues.append(f"Meta description too short: '{meta_desc.get('content', '').strip()}'.")
            recommendations.append({
                "recommendation": "Expand your meta description to 150-160 characters.",
                "why": "Short descriptions do not effectively summarize your page for search engines or potential visitors.",
                "urgency": "Medium"
            })

        # Headings extraction
        for i in range(1, 7):
            tag = f'h{i}'
            tags_found = soup.find_all(tag)
            for t in tags_found:
                text = t.get_text(strip=True)
                if text:
                    headings_found[tag].append(text)

        headings_count = len(headings_found['h1'])
        if headings_count == 0:
            general_issues.append("No <h1> tag found.")
            recommendations.append({
                "recommendation": "Add a descriptive <h1> tag.",
                "why": "<h1> tags help search engines and users understand the primary topic of the page, aiding SEO and structure.",
                "urgency": "High"
            })
        elif headings_count > 1:
            general_issues.append(f"Multiple <h1> tags found: {headings_count}.")
            recommendations.append({
                "recommendation": "Use only one <h1> tag per page.",
                "why": "Multiple <h1> tags can confuse search engines and reduce the clarity of your page's focus.",
                "urgency": "High"
            })

        # Images without alt
        images = soup.find_all('img')
        for img in images:
            if not img.get('alt'):
                img_src = img.get('src') or img.get('data-src') or "Unknown src"
                if img_src.startswith("//"):
                    img_src = "https:" + img_src
                elif img_src.startswith("/"):
                    img_src = urljoin(url, img_src)
                missing_alt_images.append(img_src)
        if missing_alt_images:
            general_issues.append(f"{len(missing_alt_images)} images missing alt attributes.")
            recommendations.append({
                "recommendation": "Add descriptive alt text to all images.",
                "why": "Alt text improves accessibility for visually impaired users and helps search engines understand your images, boosting SEO.",
                "urgency": "Medium"
            })

        # Broken links
        links = soup.find_all('a', href=True)
        base_url = "{0.scheme}://{0.netloc}".format(urlparse(url))
        checked = set()
        for link in links:
            href = link['href']
            if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                continue
            if href.startswith('/'):
                full_url = urljoin(base_url, href)
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = urljoin(url, href)
            if full_url in checked:
                continue
            checked.add(full_url)
            try:
                resp = requests.head(full_url, allow_redirects=True, timeout=5)
                if resp.status_code >= 400:
                    broken_links.append(full_url)
            except:
                broken_links.append(full_url)
        if broken_links:
            general_issues.append(f"{len(broken_links)} broken links found.")
            recommendations.append({
                "recommendation": "Fix or remove broken links.",
                "why": "Broken links harm user experience, increase bounce rates, and negatively impact your SEO rankings.",
                "urgency": "High"
            })

        # Design Layout Recommendations
        design_recommendations = [
            {
                "recommendation": "Ensure your website uses a clean, uncluttered layout with clear section separation.",
                "why": "A clean layout helps visitors find what they need quickly, reducing bounce rates and improving conversions.",
                "urgency": "Medium"
            },
            {
                "recommendation": "Check that your website is mobile responsive and easy to navigate on all devices.",
                "why": "Over 50% of web traffic comes from mobile devices, and a poor mobile experience can cause visitors to leave.",
                "urgency": "High"
            },
            {
                "recommendation": "Use consistent fonts and color schemes across your pages.",
                "why": "Consistency builds brand trust and makes your site appear professional.",
                "urgency": "Medium"
            },
            {
                "recommendation": "Ensure you have clear Calls to Action (CTAs) on your pages.",
                "why": "CTAs guide visitors to take the next step, whether contacting you, booking a service, or purchasing, increasing your conversions.",
                "urgency": "High"
            }
        ]
        recommendations.extend(design_recommendations)

    except Exception as e:
        general_issues.append(f"Error accessing site: {e}")
        recommendations.append({
            "recommendation": "Ensure your site is live and accessible.",
            "why": "If your site is down, visitors and search engines cannot access it, which can harm your rankings and trust.",
            "urgency": "High"
        })

    return {
        "general_issues": general_issues,
        "recommendations": recommendations,
        "missing_alt_images": missing_alt_images[:6],
        "headings_found": headings_found,
        "broken_links": broken_links,
    }

def home(request):
    if request.method == 'POST':
        form = URLScanForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['url']
            scan_data = scan_website(url)

            title = ""
            try:
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, 'html.parser')
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.text.strip()
            except:
                pass

            layout_suggestions = generate_layout_suggestions(title, scan_data["headings_found"], url)

            WebsiteScan.objects.create(
                url=url,
                issues_found="\n".join(scan_data["general_issues"]),
                recommendations="\n".join([rec["recommendation"] for rec in scan_data["recommendations"]]),
            )

            return render(request, 'website_analyzer/results.html', {
                "url": url,
                **scan_data,
                "layout_suggestions": layout_suggestions
            })
    else:
        form = URLScanForm()
    return render(request, 'website_analyzer/home.html', {'form': form})

