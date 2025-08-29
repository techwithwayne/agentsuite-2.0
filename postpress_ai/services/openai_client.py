# agentsuite/postpress_ai/openai_client.py
"""
PostPress AI — Simple preview stub generator.

Why this file?
--------------
Your /postpress-ai/preview/ endpoint calls a stubbed generator during development.
Previously, that stub **combined the subject and genre into the title** like:
    f"{subject} — {genre}"
which caused the preview to show "Ai Growth — How-to" as the Title.

This version fixes that by:
- Using the **subject ONLY** for the `title` field and the <h1>.
- Keeping Tone/Genre in an italic byline below the H1.
- Preserving the response contract: { ok, result:{title, html, summary}, token_usage? }.
- Escaping user-provided values for safe HTML.
- Adding debug logging so you can verify inputs/outputs in Django logs.

If/when you switch from this stub to live Assistant v2 output, keep the same shape.
"""

from __future__ import annotations

import html
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _safe(s: str | None) -> str:
    """HTML-escape any user-provided string; return empty string for None."""
    return html.escape((s or "").strip(), quote=True)


def generate_article(subject: str | None = "",
                     genre: str | None = "",
                     tone: str | None = "") -> Dict[str, Any]:
    """
    Return a PREVIEW article payload.

    Parameters
    ----------
    subject : str
        The main topic (this becomes the Title exactly, without genre appended).
    genre : str
        Content style such as "How-to", "Guide", etc. Shown in the byline only.
    tone : str
        Voice such as "Friendly", "Professional". Shown in the byline only.

    Returns
    -------
    dict
        {
          "title": <subject_only>,
          "html":  "<full HTML snippet>",
          "summary": "short sentence used above the preview frame",
          "token_usage": {"prompt": 0, "completion": 0, "total": 0}  # optional
        }
    """

    # Sanitize/normalize inputs for display
    subj = _safe(subject) or "Untitled"
    genr = _safe(genre) or "General"
    tone_safe = _safe(tone) or "Neutral"

    # IMPORTANT FIX:
    # Title must be the SUBJECT ONLY (no genre concatenation).
    title = subj

    # Keep Tone/Genre in an italic byline, separate from H1.
    byline = f"<p><em>Tone: {tone_safe} • Genre: {genr}</em></p>"

    # A short summary used by the admin UI; keep it simple and neutral.
    summary = f"Preview summary for {subj} in {genr} with {tone_safe} tone."

    # The main HTML that will render inside the preview iframe/panel.
    # We include headings and a simple list so your Exact-HTML tests continue to work.
    html_snippet = f"""
<div class="ppa-preview">
  <h1>{title}</h1>
  {byline}
  <p>This is a generated preview article about <strong>{title}</strong>.
     Replace this stub with live Assistant v2 output from your existing integration.
     Keep semantic HTML, headings, and lists for readability and SEO.</p>

  <h2>Key Points</h2>
  <ul>
    <li>Introduce the topic clearly</li>
    <li>Explain benefits or insights</li>
    <li>Provide actionable steps</li>
  </ul>

  <p>Conclusion and CTA suited for your audience in Iowa and beyond.</p>
</div>
""".strip()

    payload = {
        "title": title,
        "html": html_snippet,
        "summary": summary,
        # Optional token bookkeeping (zeros in stub to avoid confusion)
        "token_usage": {"prompt": 0, "completion": 0, "total": 0},
    }

    # Helpful debug line you can watch in Django logs during the mini-test.
    logger.debug(
        "[PPA][openai_client] generate_article inputs: subject=%r genre=%r tone=%r -> title=%r",
        subject, genre, tone, title
    )

    return payload
