"""
Assistant runner for PostPress AI (Chat Completions).

CHANGE LOG
----------
2026-01-14 • PROMPT: Update system/user prompts to be global, creator+agency lane-aware, respectful to knowledgeable brief-writers, and avoid checkbox task-list markers.  # CHANGED

2025-11-18 • Switch /generate/ from Assistants v2 + tools to a single Chat Completions call with JSON output, keeping the same normalized contract.  # CHANGED:
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
- Does NOT alter the public JSON response shape used by WordPress proxy or admin.js.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - import guard
    OpenAI = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


def strip_code_fences(raw: str) -> str:
    """
    Remove surrounding ```json ... ``` fences if the model returns them.
    Some Chat Completions models still like to wrap JSON this way.
    """
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text.startswith("```"):
        # Strip first line ``` or ```json
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        # Strip trailing fence if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def safe_json_loads(raw: str) -> Dict[str, Any]:
    """
    Parse JSON with a bit of resilience:
    - Strip Markdown code fences.
    - If parsing fails, raise ValueError with a short message.
    """
    txt = strip_code_fences(raw)
    try:
        data = json.loads(txt)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Could not parse JSON from assistant: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Assistant JSON root must be an object")
    return data


def enforce_yoast_limits(title: str, meta_description: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Enforce Yoast-like limits on title + meta description:
    - Title ~<= 60 chars
    - Meta description ~<= 155 chars
    """
    t = (title or "").strip()
    if len(t) > 600:
        t = t[:57].rstrip() + "…"

    if meta_description is None:
        return t, None

    m = meta_description.strip()
    if len(m) > 155:
        m = m[:152].rstrip() + "…"

    return t, m


def compute_slug(title: str) -> str:
    """
    Compute a slug from the title.
    Keep it URL-safe and lowercase; remove non-word chars.
    """
    import re

    t = (title or "").strip().lower()
    # Remove HTML tags if any were introduced.
    t = re.sub(r"<[^>]+>", "", t)
    # Normalize unicode accents where possible
    try:
        import unicodedata

        t = unicodedata.normalize("NFKD", t)
    except Exception:  # pragma: no cover - very narrow edge
        pass
    # Remove non-word characters, keep spaces/hyphens
    t = re.sub(r"[^\w\s-]+", "", t)
    # Collapse whitespace to single hyphens
    t = re.sub(r"\s+", "-", t)
    # Collapse multiple hyphens
    t = re.sub(r"-+", "-", t)
    # Trim leading/trailing hyphens
    t = t.strip("-")
    return t or "post"


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
    subject: Optional[str],
    title: Optional[str],
    body: Optional[str],
    hints: Optional[List[str]] = None,
) -> str:
    """
    Derive a focus keyphrase in a stable way:
    - Prefer first hint if provided.
    - Else prefer subject > title > salient body tokens.
    Ensures 'Iowa' presence when natural (avoid keyword stuffing).
    """
    if hints:
        kp = hints[0]
    elif subject:
        kp = subject
    elif title:
        kp = title
    elif body:
        text = body.strip().splitlines()[0]
        kp = text[:80]
    else:
        kp = "Iowa small business website tips"

    kp = kp.strip()

    # Remove hyphens for Yoast keyphrase (Wayne's rule).
    kp = kp.replace("-", " ")

    # Ensure Iowa appears naturally if not present.
    if "iowa" not in kp.lower():
        kp = kp + " in Iowa"

    return kp


def _normalize_assistant_output(
    subject: Optional[str],
    keywords: List[str],
    raw: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize the assistant JSON into the contract:

    {
      "title": str,
      "outline": [str, ...],
      "body_markdown": str,
      "meta": {
        "focus_keyphrase": str,
        "meta_description": str,
        "slug": str
      }
    }

    We intentionally keep Yoast rules and slug logic on the server side
    so UI/JS can stay simpler and we can reuse this for other surfaces.
    """
    title = (raw.get("title") or "").strip()
    outline_raw = raw.get("outline") or []
    if not isinstance(outline_raw, list):
        outline_raw = []

    body_markdown = (raw.get("body_markdown") or raw.get("body") or "").strip()

    meta_dict = raw.get("meta") or {}
    if not isinstance(meta_dict, dict):
        meta_dict = {}

    # Compute focus keyphrase if missing or empty
    focus = (meta_dict.get("focus_keyphrase") or "").strip()
    if not focus:
        focus = extract_focus_keyphrase(
            subject=subject or title or None,
            title=title or None,
            body=body_markdown or None,
            hints=keywords,
        )

    yoast_limits = enforce_yoast_limits(title)
    meta_description_raw = meta_dict.get("meta_description")
    if isinstance(meta_description_raw, str):
        _, meta_description = enforce_yoast_limits(title, meta_description_raw)
    else:
        _, meta_description = yoast_limits

    slug_raw = (meta_dict.get("slug") or "").strip()
    if not slug_raw:
        slug_raw = compute_slug(title)

    normalized = {
        "title": yoast_limits[0],
        "outline": outline_raw,
        "body_markdown": body_markdown,
        "meta": {
            "focus_keyphrase": focus,
            "meta_description": meta_description,
            "slug": slug_raw,
        },
    }
    return normalized


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
            or "gpt-4.1-mini"
        )

    # ---------------------------------------------------------------------  # /generate/
    def run_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entrypoint for /generate/ view.
        Uses a single Chat Completion call that returns JSON.
        """
        subject = (payload.get("subject") or "").strip()
        genre = (payload.get("genre") or "").strip() or "How-to"
        tone = (payload.get("tone") or "").strip() or "Friendly"
        audience = (payload.get("audience") or "") or None

        # Derive target length from explicit payload length or word_count (preferred)                   # CHANGED:
        raw_len = (payload.get("length") or "").strip()                                              # CHANGED:
        # word_count can be sent from the UI as int or string; coerce safely                         # CHANGED:
        wc_raw = payload.get("word_count")                                                           # CHANGED:
        wc_val: int = 0                                                                              # CHANGED:
        try:                                                                                         # CHANGED:
            if isinstance(wc_raw, (int, float)):                                                     # CHANGED:
                wc_val = int(wc_raw)                                                                 # CHANGED:
            elif isinstance(wc_raw, str) and wc_raw.strip():                                         # CHANGED:
                wc_val = int(float(wc_raw.strip()))                                                  # CHANGED:
        except Exception:                                                                            # CHANGED:
            wc_val = 0                                                                               # CHANGED:
        # Clamp to a reasonable blog range if provided                                               # CHANGED:
        if wc_val and wc_val < 300:                                                                  # CHANGED:
            wc_val = 300                                                                             # CHANGED:
        elif wc_val and wc_val > 6000:                                                               # CHANGED:
            wc_val = 6000                                                                            # CHANGED:
        if wc_val:                                                                                   # CHANGED:
            length = f"~{wc_val} words"                                                              # CHANGED:
        elif raw_len:                                                                                # CHANGED:
            length = raw_len                                                                         # CHANGED:
        else:                                                                                        # CHANGED:
            length = "~1500 words"                                                                   # CHANGED:

        raw_keywords = payload.get("keywords") or []
        if isinstance(raw_keywords, str):
            keywords = [raw_keywords]
        elif isinstance(raw_keywords, list):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        # ------------------------- PROMPTS (UPDATED) ------------------------- #
        system_prompt = (
            "You are PostPress AI — a seasoned editor and strategist who writes like a real human. "  # CHANGED
            "Assume the person providing the brief knows their craft (capable practitioner, not a beginner). "  # CHANGED
            "Write with respect: no lecturing, no condescension, no ego, no 'guru' tone. Confident but grounded. "  # CHANGED
            "If the brief explicitly requests a different voice (more bold, playful, punchy, edgy, etc.), follow the brief exactly. "  # CHANGED
            "\n"  # CHANGED
            "Your audience is global and mixed. You work across two primary lanes: "  # CHANGED
            "1) Creators (personal brands, portfolios, publishing, products, solo work) and "  # CHANGED
            "2) Agencies/Teams (client work, retainers, delivery, positioning, proposals, team dynamics). "  # CHANGED
            "\n"  # CHANGED
            "Lane rule (critical): "  # CHANGED
            "Infer the primary working context from the brief (topic, audience, tone, genre, keywords, industry, goal if present). "  # CHANGED
            "If the brief implies client work, retainers, audits, proposals, pipeline, or team delivery → write primarily for Agency/Team. "  # CHANGED
            "If it implies publishing cadence, audience growth, personal brand, creator products, or solo work → write primarily for Creator. "  # CHANGED
            "If it's mixed or unclear → include a short split section titled 'If you're a creator…' and 'If you're an agency/team…' (2–5 bullets each). "  # CHANGED
            "\n"  # CHANGED
            "How you write: "  # CHANGED
            "Personal, calm, specific. No hype. No robotic filler. No 'Certainly.' No 'In today’s digital world…'. "  # CHANGED
            "Write like a peer: helpful, not preachy. Don’t over-explain basics they likely already know. "  # CHANGED
            "Prefer practical nuance: tradeoffs, sequence, priorities, and what to do next. "  # CHANGED
            "Use stats only if the brief provides them. If you include an example, label it as hypothetical. "  # CHANGED
            "Never invent facts, stats, quotes, dates, awards, clients, or case studies. "  # CHANGED
            "\n"  # CHANGED
            "Structure (in order): "  # CHANGED
            "1) Empathetic hook (6–10 lines that show you understand their real problem). "  # CHANGED
            "2) 2–4 reasons they’re stuck (specific to their world, not generic). "  # CHANGED
            "3) Prioritized plan: quick wins first, then deeper moves (clear priority). "  # CHANGED
            "4) Checklist they can use today (plain bullets only — NO [ ], [x], ☐, ✅). "  # CHANGED
            "5) Common mistakes in their space (not universal platitudes). "  # CHANGED
            "6) Two paths forward: DIY next step + one gentle option. "  # CHANGED
            "\n"  # CHANGED
            f"Length & format: About {wc_val or 1500} words. Markdown with clean headings (#, ##, ###). "  # CHANGED
            "Short paragraphs. Feels natural, not templated. "  # CHANGED
            "\n"  # CHANGED
            "Conversion paths (lane-specific): "  # CHANGED
            "Creator lane → subscribe, download, buy, waitlist, collaboration, newsletter. "  # CHANGED
            "Agency/Team lane → discovery call, audit, proposal, retainer, RFQ, consultation. "  # CHANGED
            "Only discuss checkout/cart if ecommerce is clearly implied in the brief. "  # CHANGED
            "\n"  # CHANGED
            "SEO (natural): "  # CHANGED
            "Provide meta.focus_keyphrase (2–6 words), meta.meta_description (≤155 chars), and meta.slug (lowercase, hyphenated, 3–8 words). "  # CHANGED
            "Use the focus keyphrase naturally in the title (or close synonym) and early in the body, then let it breathe. "  # CHANGED
            "\n"  # CHANGED
            "If something critical is missing, add an 'Assumptions' section near the end (3–6 bullets). "  # CHANGED
            "\n"  # CHANGED
            "OUTPUT FORMAT (critical): Return ONLY a single JSON object. No code fences. No extra text. "  # CHANGED
            "Required keys exactly: title, outline, body_markdown, meta:{focus_keyphrase, meta_description, slug}. "  # CHANGED
            "Do not add any other keys. Ensure valid JSON and properly escaped strings."  # CHANGED
        )  # CHANGED

        user_content = (
            "Let's write something real.\n\n"  # CHANGED
            "The person behind this brief knows their craft. They want clean thinking, useful framing, and a plan that respects their expertise. "  # CHANGED
            "No lectures. No fluff. No ego.\n\n"  # CHANGED
            "Brief:\n"  # CHANGED
            f"Topic: {subject}\n"  # CHANGED
            f"Tone: {tone}\n"  # CHANGED
            f"Genre: {genre}\n"  # CHANGED
            f"Reader: {audience or 'creators and agencies/service businesses'}\n"  # CHANGED
            f"Word target: {length}\n"  # CHANGED
            f"Keywords (natural, never forced): {', '.join(keywords) if keywords else 'none'}\n\n"  # CHANGED
            "How to nail it:\n"  # CHANGED
            "- Infer the lane (creator vs agency/team) from the brief. If mixed/unclear, include a split section: "  # CHANGED
            "'If you're a creator…' and 'If you're an agency/team…' (2–5 bullets each).\n"  # CHANGED
            "- Write like a peer: confident, grounded, respectful (never pompous).\n"  # CHANGED
            "- Use examples and language that belong in their actual industry.\n"  # CHANGED
            "- Use the right conversion path for the lane. Only talk checkout/cart if ecommerce is clearly implied.\n"  # CHANGED
            "- No invented stats, quotes, dates, or case studies. Label examples as hypothetical.\n"  # CHANGED
            "- Checklist: plain bullets (- or *). No [ ], [x], ☐, or ✅.\n"  # CHANGED
            "- If the brief specifies tone or approach, that overrides everything else.\n\n"  # CHANGED
            "Return the JSON object only. Nothing else. Follow the exact keys from the system message."  # CHANGED
        )  # CHANGED
        # -------------------------------------------------------------------- #

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
                elif isinstance(first_part, dict) and "text" in first_part:
                    content_text = str(first_part["text"])
                else:
                    content_text = str(message.content)
            else:
                # Older-style: message.content is already a string
                content_text = getattr(message, "content", None) or ""
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[PPA] Could not extract content from Chat response: %s", exc, exc_info=True)
            raise

        if not content_text:
            raise ValueError("Assistant returned empty content")

        try:
            data = safe_json_loads(content_text)
        except Exception as exc:
            logger.error("[PPA] Could not parse assistant JSON: %s", exc, exc_info=True)
            raise

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
