# agentsuite/postpress_ai/assistant_runner.py
"""
Assistant v2 runner for PostPress AI.
- Creates/runs an OpenAI Assistant with server-side tool calling.
- Tools are deterministic helpers to keep the model on rails:
  * enforce_yoast_limits(title, max_len=60, max_meta_len=155)
  * compute_slug(title)
  * outline_sections(topic, audience=None, length="~2000 words")
  * title_variants(subject, tone=None, genre=None)
  * extract_focus_keyphrase(subject=None, body=None, hints=None)
- Returns a structured payload for the WP admin UI:
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

Notes:
- Handles both `.text.value` and dict-like message content formats.
- Assistant ID can be provided via settings.PPA_ASSISTANT_ID or env PPA_ASSISTANT_ID.
- Falls back to ephemeral assistant if not provided.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from django.conf import settings

# OpenAI Assistants v2
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


def extract_focus_keyphrase(subject: Optional[str] = None,
                            body: Optional[str] = None,
                            hints: Optional[List[str]] = None) -> str:
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


# ---------------------------
# Assistant Runner
# ---------------------------
class AssistantRunner:
    def __init__(self):
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=api_key)

        # Allow configured assistant id, else use ephemeral one
        self.assistant_id = (
            getattr(settings, "PPA_ASSISTANT_ID", None)
            or os.getenv("PPA_ASSISTANT_ID")
            or None
        )

    def _build_tools(self) -> List[Dict[str, Any]]:
        """
        Define JSON-schema tools that Assistant v2 can call.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "enforce_yoast_limits",
                    "description": "Trim a proposed SEO title and suggest a meta description hint within Yoast-friendly limits.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "max_len": {"type": "integer", "default": 60},
                            "max_meta_len": {"type": "integer", "default": 155},
                        },
                        "required": ["title"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compute_slug",
                    "description": "Compute a WordPress-safe hyphenated slug from a title.",
                    "parameters": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "outline_sections",
                    "description": "Return a sensible outline for a long-form blog post.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "audience": {"type": "string"},
                            "length": {"type": "string", "default": "~2000 words"},
                        },
                        "required": ["topic"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "title_variants",
                    "description": "Return 3–6 deterministic title seeds.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "tone": {"type": "string"},
                            "genre": {"type": "string"},
                        },
                        "required": ["subject"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "extract_focus_keyphrase",
                    "description": "Extract a natural-sounding focus keyphrase with 'Iowa' when appropriate.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                            "hints": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        ]

    def _ensure_assistant(self) -> str:
        """
        Use configured assistant if available; else create ephemeral Assistant
        with our tools and strict JSON output instructions.
        """
        if self.assistant_id:
            return self.assistant_id

        logger.debug("[PPA] Creating ephemeral Assistant for this run.")
        a = self.client.beta.assistants.create(
            name="PostPress AI Writer",
            instructions=(
                "You are a senior content strategist for PostPress AI. "
                "You will produce long-form, human, helpful content for small businesses in Iowa. "
                "Always respect Yoast ranges (title <= ~60 chars, meta <= ~155 chars). "
                "Prefer natural phrasing over keyword stuffing. "
                "When helpful, call the provided tools. "
                "Return your FINAL answer as STRICT JSON only with keys: "
                "{title, outline, body_markdown, meta:{focus_keyphrase, meta_description, slug}}. "
                "Do not include Markdown code fences around the JSON."
            ),
            tools=self._build_tools(),
            model=getattr(settings, "PPA_ASSISTANT_MODEL", "gpt-4o-mini"),
        )
        self.assistant_id = a.id
        return self.assistant_id

    def run_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entrypoint for /generate/ view.
        """
        assistant_id = self._ensure_assistant()

        subject = payload.get("subject", "").strip()
        genre = payload.get("genre", "").strip() or "How-to"
        tone = payload.get("tone", "").strip() or "Friendly"
        audience = payload.get("audience", "") or None
        length = payload.get("length", "") or "~2000 words"
        keywords = payload.get("keywords") or []

        user_msg = {
            "role": "user",
            "content": (
                "Please generate a blog post.\n"
                f"Subject: {subject}\n"
                f"Genre: {genre}\n"
                f"Tone: {tone}\n"
                f"Audience: {audience or 'general small business owners'}\n"
                f"Target length: {length}\n"
                f"Keywords (optional, non-stuffed): {', '.join(keywords) if keywords else 'none'}\n\n"
                "Output strictly as JSON with keys: title, outline, body_markdown, meta:{focus_keyphrase, meta_description, slug}.\n"
                "If you need scaffolding, call the tools. Otherwise, produce final JSON."
            ),
        }

        thread = self.client.beta.threads.create()
        self.client.beta.threads.messages.create(thread_id=thread.id, **user_msg)
        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id,
        )

        # Poll until completion (handling tool calls)
        while True:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            status = run.status
            logger.debug(f"[PPA] Run status: {status}")

            if status == "completed":
                break
            if status == "failed":
                raise RuntimeError(f"Assistant run failed: {getattr(run, 'last_error', None)}")
            if status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls  # type: ignore[attr-defined]
                outputs = []
                for call in tool_calls:
                    name = call.function.name
                    args = json.loads(call.function.arguments or "{}")
                    logger.debug(f"[PPA] Tool call: {name}({args})")

                    if name == "enforce_yoast_limits":
                        result = enforce_yoast_limits(**args)
                    elif name == "compute_slug":
                        result = {"slug": compute_slug(**args)}
                    elif name == "outline_sections":
                        result = {"outline": outline_sections(**args)}
                    elif name == "title_variants":
                        result = {"titles": title_variants(**args)}
                    elif name == "extract_focus_keyphrase":
                        result = {"focus_keyphrase": extract_focus_keyphrase(**args)}
                    else:
                        result = {"error": f"Unknown tool: {name}"}

                    outputs.append({"tool_call_id": call.id, "output": json.dumps(result)})

                self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=outputs,
                )
                continue

        # Collect latest assistant message
        msgs = self.client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=5)
        content_text: Optional[str] = None

        for m in msgs.data:
            if m.role != "assistant":
                continue
            # Handle both formats: .text.value and dict blobs
            if m.content and hasattr(m.content[0], "text") and hasattr(m.content[0].text, "value"):
                content_text = m.content[0].text.value
            else:
                try:
                    # Some SDKs return dict-like structures
                    chunk = m.content[0]
                    if isinstance(chunk, dict):
                        if "text" in chunk and isinstance(chunk["text"], dict) and "value" in chunk["text"]:
                            content_text = chunk["text"]["value"]
                except Exception:
                    pass

            if content_text:
                break

        if not content_text:
            raise RuntimeError("No assistant content returned.")

        # Try strict JSON first
        data: Dict[str, Any]
        try:
            data = json.loads(content_text)
        except json.JSONDecodeError:
            # Fallback: create a minimal JSON from text
            logger.debug("[PPA] Assistant returned non-JSON text; building fallback.")
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

        # Ensure required keys exist
        data.setdefault("title", subject or "Untitled")
        data.setdefault("outline", outline_sections(subject or "Your Topic"))
        data.setdefault("body_markdown", "")
        data.setdefault("meta", {})
        data["meta"].setdefault("focus_keyphrase", extract_focus_keyphrase(subject=subject, hints=keywords))
        data["meta"].setdefault("meta_description", enforce_yoast_limits(data["title"])["meta_hint"])
        data["meta"].setdefault("slug", compute_slug(data["title"]))

        return data


def run_postpress_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    External entrypoint used by the view.
    Separated for easy testing/mocking.
    """
    runner = AssistantRunner()
    return runner.run_generate(payload)
