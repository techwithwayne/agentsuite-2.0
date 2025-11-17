"""
Assistant runner for PostPress AI (Chat Completions).

CHANGE LOG
----------
2025-11-18 • Switch /generate/ from Assistants v2 + tools to a single Chat Completion with JSON output, keeping the same normalized contract.  # CHANGED:
2025-11-17 • Add bounded polling (max wait) + brief sleep to avoid long cURL timeouts from WP and surface structured errors instead.
2025-11-16 • Harden JSON parsing, strip code fences, normalize output shape, and enforce Yoast/slug/keyphrase rules server-side (A–D: structure, quality, tools, hardening).

- Uses OpenAI Chat Completions with response_format='json_object' to generate:
  * title: str
  * outline: list[str]
  * body_markdown: str
  * meta: { focus_keyphrase, meta_description, slug }
- Keeps deterministic Python helpers (enforce_yoast_limits, compute_slug, outline_sections,
  extract_focus_keyphrase) on the server side for consistency and SEO rules.

Notes:
- Keeps the external contract for run_postpress_generate(payload) unchanged.
- Does NOT use Assistants threads/runs or tools anymore for /generate/.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from django.conf import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

import logging
logger = logging.getLogger(__name__)


# ---------------------------
# Helper (deterministic) tools
# ---------------------------
def enforce_yoast_limits(title: str, max_len: int = 60, max_meta_len: int = 155) -> Dict[str, Any]:
    """
    Trim a proposed SEO title and meta description boundary hints.
    Returns guidance only; model still crafts final text.
    """
    safe_title = title.strip()
    if len(safe_title) > max_len:
        safe_title = safe_title[: max_len - 1].rstrip(" -–—:") + "…"
    # Provide a templated meta description hint the model can refine.
    hint_meta = f"{safe_title} – actionable tips for small businesses in Iowa."
    if len(hint_meta) > max_meta_len:
        hint_meta = hint_meta[: max_meta_len - 1].rstrip(" -–—:") + "…"
    return {"title_hint": safe_title, "meta_hint": hint_meta, "max_title": max_len, "max_meta": max_meta_len}


def compute_slug(title: str) -> str:
    """
    Convert a title into a WP-friendly, hyphenated slug.
    (Per Wayne’s rule, permalinks use hyphenation; keyphrases/alt text do not.)
    """
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "post"


def outline_sections(topic: str, audience: Optional[str] = None, length: str = "~2000 words") -> List[str]:
    """
    Provide a sensible default outline for long-form posts.
    The model can call this as a scaffold, then expand in prose.
    """
    base = [
        "Introduction: why this matters in Iowa",
        "The problem (with a quick story)",
        "Step-by-step solution",
        "Common pitfalls and how to avoid them",
        "Tools and resources",
        "Local tips for Mount Vernon, Marion, and Cedar Rapids",
        "Conclusion + clear call to action",
    ]
    if audience:
        base.insert(1, f"Who this is for: {audience}")
    return base


def title_variants(subject: str, tone: Optional[str] = None, genre: Optional[str] = None) -> List[str]:
    """
    Offer deterministic title seeds the model can choose/refine from.
    (Currently not called in the Chat Completions path, but kept for future tools/features.)
    """
    tone = (tone or "friendly").lower()
    genre = (genre or "how-to").lower()
    seeds = [
        f"{subject}: A Practical {genre.title()} Guide for Iowa",
        f"Fix {subject} Fast: A {tone.title()} Walkthrough for Small Businesses",
        f"{subject} in Plain English (Iowa Edition)",
        f"From Confusion to Clarity: {subject} Explained",
        f"Stop Struggling with {subject}: The No-Fluff Guide",
    ]
    return seeds


def extract_focus_keyphrase(
    subject: Optional[str] = None,
    body: Optional[str] = None,
    hints: Optional[List[str]] = None,
) -> str:
    """
    Naive extractor that prefers provided hints > subject > salient body tokens.
    Ensures 'Iowa' presence when natural (avoid keyword stuffing).
    """
    if hints:
        kp = hints[0]
    elif subject:
        kp = subject
    else:
        # Very simple fallback: pick a 2–4 word noun-ish phrase from body.
        kp = "website performance in Iowa"

    # Ensure natural Iowa presence
    if "iowa" not in kp.lower():
        kp = f"{kp} in Iowa"
    # Remove hyphens for keyphrase per Wayne’s rule
    kp = kp.replace("-", " ")
    return kp.strip()


def _strip_code_fences(text: str) -> str:
    """
    Remove leading/trailing ``` or ```json fences if present and return inner content.
    Safe no-op if no fences are found.
    """
    if not text:
        return text
    s = text.strip()
    if s.startswith("```"):
        # Prefer the first fenced block if present
        m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
        if m:
            return m.group(1).strip()
        lines = s.splitlines()
        if len(lines) >= 2:
            if lines[0].startswith("```") and lines[-1].startswith("```"):
                return "\n".join(lines[1:-1]).strip()
            return "\n".join(lines[1:]).strip()
    return text


def _normalize_assistant_output(subject: str, keywords: List[str], raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize model output into the strict PostPress AI contract.
    Guarantees: title (str), outline (list[str]), body_markdown (str),
    meta: {focus_keyphrase, meta_description, slug}.
    """
    safe_subject = (subject or "").strip()
    title = str(raw.get("title") or safe_subject or "Untitled").strip()
    if not title:
        title = "Untitled"

    outline_raw = raw.get("outline")
    outline: List[str] = []
    if isinstance(outline_raw, list):
        outline = [str(x).strip() for x in outline_raw if str(x).strip()]
    elif outline_raw:
        outline = [str(outline_raw).strip()]
    if not outline:
        outline = outline_sections(title)

    body_markdown = str(raw.get("body_markdown") or "").strip()

    meta_in = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    meta_dict: Dict[str, Any] = dict(meta_in) if isinstance(meta_in, dict) else {}

    focus_keyphrase = extract_focus_keyphrase(
        subject=title or safe_subject or None,
        body=body_markdown or None,
        hints=keywords,
    )

    yoast_limits = enforce_yoast_limits(title)
    meta_description_raw = meta_dict.get("meta_description")
    if meta_description_raw:
        meta_description = str(meta_description_raw).strip()
    else:
        meta_description = yoast_limits["meta_hint"]

    max_meta = yoast_limits.get("max_meta", 155)
    if len(meta_description) > max_meta:
        meta_description = meta_description[: max_meta - 1].rstrip(" -–—:") + "…"

    slug = compute_slug(title)

    # Preserve any extra meta keys but ensure our core fields take precedence.
    extra_meta = {
        k: v for k, v in meta_dict.items() if k not in {"focus_keyphrase", "meta_description", "slug"}
    }

    meta = {
        "focus_keyphrase": focus_keyphrase,
        "meta_description": meta_description,
        "slug": slug,
        **extra_meta,
    }

    return {
        "title": title,
        "outline": outline,
        "body_markdown": body_markdown,
        "meta": meta,
    }


# ---------------------------
# Chat Completion Runner
# ---------------------------
class AssistantRunner:
    """
    Thin wrapper around OpenAI Chat Completions for /generate/.
    Keeps external behavior identical while simplifying internals.
    """

    def __init__(self) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=api_key)
        # Allow overriding the chat model via settings or env; default to a fast GPT-4 class model.
        self.model = (
            getattr(settings, "PPA_CHAT_MODEL", None)
            or os.getenv("PPA_CHAT_MODEL")
            or getattr(settings, "PPA_ASSISTANT_MODEL", "gpt-4o-mini")  # reuse existing setting if present
        )

    def run_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entrypoint for /generate/ view.
        Uses a single Chat Completion call that returns JSON.
        """
        subject = (payload.get("subject") or "").strip()
        genre = (payload.get("genre") or "").strip() or "How-to"
        tone = (payload.get("tone") or "").strip() or "Friendly"
        audience = (payload.get("audience") or "") or None
        length = (payload.get("length") or "") or "~1500 words"

        raw_keywords = payload.get("keywords") or []
        if isinstance(raw_keywords, str):
            keywords = [raw_keywords]
        elif isinstance(raw_keywords, list):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        system_prompt = (
            "You are PostPress AI, a senior content strategist writing for small business owners in Iowa. "
            "You generate long-form, human, helpful blog posts with clear Markdown headings and minimal fluff. "
            "Your response MUST be a single JSON object with keys: "
            "title, outline, body_markdown, meta:{focus_keyphrase, meta_description, slug}. "
            "Do not include any extra commentary, explanations, or Markdown code fences. "
            "Aim for roughly 1200–1800 words of useful content in body_markdown. "
            "Respect Yoast-style ranges (title ~<= 60 chars, meta_description ~<= 155 chars) and avoid keyword stuffing."
        )

        user_content = (
            "Generate a long-form blog post draft for small business owners.\n"
            f"Subject: {subject}\n"
            f"Genre: {genre}\n"
            f"Tone: {tone}\n"
            f"Audience: {audience or 'general small business owners'}\n"
            f"Target length: {length}\n"
            f"Keywords (optional, non-stuffed): {', '.join(keywords) if keywords else 'none'}\n\n"
            "Return only JSON with the exact keys requested in the system message. "
            "Use Markdown headings (#, ##, ###) in body_markdown."
        )

        logger.info("[PPA] Chat generate start: subject=%r, model=%s", subject, self.model)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        except Exception as exc:
            logger.error("[PPA] Chat completion error: %s", exc, exc_info=True)
            raise

        # Extract text content from the first choice.
        content_text: Optional[str] = None
        try:
            choice = response.choices[0]
            message = choice.message

            # Newer SDKs: message.content is a list of content parts
            if getattr(message, "content", None):
                first_part = message.content[0]
                if hasattr(first_part, "text") and hasattr(first_part.text, "value"):
                    content_text = first_part.text.value
                else:
                    # Fallback: try plain content string
                    content_text = str(getattr(message, "content", "")) or None
            else:
                # Older-style: message.content is just a string
                content_text = str(getattr(message, "content", "")) or None
        except Exception as parse_exc:
            logger.error("[PPA] Failed to extract chat content: %s", parse_exc, exc_info=True)
            raise RuntimeError("Failed to extract content from chat completion response") from parse_exc

        if not content_text:
            raise RuntimeError("No content returned from chat completion.")

        content_text = _strip_code_fences(content_text)

        # Try strict JSON first
        try:
            data: Dict[str, Any] = json.loads(content_text)
        except json.JSONDecodeError:
            logger.debug("[PPA] Chat returned non-JSON text; building fallback.")
            t = subject or "Untitled"
            data = {
                "title": t,
                "outline": outline_sections(subject or "Your Topic"),
                "body_markdown": content_text,
                "meta": {
                    "focus_keyphrase": extract_focus_keyphrase(subject=subject, hints=keywords),
                    "meta_description": f"{t} – A practical guide for Iowa small businesses.",
                    "slug": compute_slug(t),
                },
            }

        # Some models may wrap the object as {"result": {...}}; unwrap it if so.
        if "title" not in data and isinstance(data.get("result"), dict):
            data = data["result"]

        normalized = _normalize_assistant_output(
            subject=subject,
            keywords=keywords,
            raw=data,
        )
        logger.info(
            "[PPA] Chat generate done: title=%r, outline_len=%d",
            normalized.get("title"),
            len(normalized.get("outline") or []),
        )
        return normalized


def run_postpress_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    External entrypoint used by the view.
    Separated for easy testing/mocking.
    """
    runner = AssistantRunner()
    return runner.run_generate(payload)
