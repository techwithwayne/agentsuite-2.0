# agentsuite/personal_mentor/assistant.py

import os
import time
import json
from typing import Dict, Any, List, Callable, Optional, Union

from openai import OpenAI
from .tools import TOOL_SPEC, TOOL_FUNCTIONS

# ---------- env helpers ----------
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else v

OPENAI_API_KEY = _env("OPENAI_API_KEY")
ASSISTANT_ID = _env("PERSONAL_MENTOR_ASSISTANT_ID") or _env("OPENAI_ASSISTANT_ID")

RUNTIME_INSTRUCTIONS = (
    _env("PERSONAL_MENTOR_INSTRUCTIONS")
    or "You are Wayne's Personal Mentor named 'Mentor'. Be concise, concrete, and step-by-step. Ask 1-2 clarifiers when needed, then give code or actions."
)

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ---------- utils that work with dicts *or* SDK objects ----------
ContentLike = Union[dict, Any]

def _get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default

PLACEHOLDERS = {"(No reply)", "(No content returned.)", "(no reply)", "(empty)", "(null)"}

def extract_text_from_message(message: ContentLike) -> str:
    parts: List[str] = []

    # text blocks
    for block in _get(message, "content", []) or []:
        t = _get(block, "type")
        if t == "text":
            txt = _get(_get(block, "text", {}), "value")
            if isinstance(txt, str) and txt.strip():
                parts.append(txt.strip())
        elif t == "input_text":
            it = _get(block, "input_text")
            if it:
                parts.append(str(it))

    # tool outputs
    for out in _get(message, "tool_outputs", []) or []:
        v = out.get("output") if isinstance(out, dict) else None
        if v:
            parts.append(v if isinstance(v, str) else json.dumps(v))

    fb = _get(message, "response") or _get(message, "text")
    if isinstance(fb, str) and fb.strip():
        parts.append(fb.strip())

    text = "\n".join([p for p in parts if p]).strip()
    return "" if (not text or text in PLACEHOLDERS) else text

# ---------- debug preview ----------
def messages_preview(thread_id: str, limit: int = 8):
    try:
        msgs = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=limit)
        out = []
        for m in getattr(msgs, "data", []) or []:
            role = _get(m, "role") or "unknown"
            snippet = extract_text_from_message(m).strip().replace("\n", " ") or "(no text)"
            if len(snippet) > 180:
                snippet = snippet[:177] + "..."
            out.append({"role": role, "text": snippet})
        return list(reversed(out))
    except Exception as e:
        return [{"role": "system", "text": f"(preview error: {str(e)[:140]})"}]

# ---------- thin OpenAI wrappers (each guarded) ----------
def _threads_create() -> str:
    return client.beta.threads.create().id

def _messages_list(thread_id: str):
    return client.beta.threads.messages.list(thread_id=thread_id)

def _message_create(thread_id: str, role: str, text: str):
    return client.beta.threads.messages.create(thread_id=thread_id, role=role, content=text)

def _run_create(thread_id: str, assistant_id: str, instructions: Optional[str]):
    return client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        instructions=instructions or RUNTIME_INSTRUCTIONS,
        tools=TOOL_SPEC or None,
    )

def _run_retrieve(thread_id: str, run_id: str):
    return client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)

def _submit_tool_outputs(thread_id: str, run_id: str, tool_outputs: List[Dict[str, str]]):
    return client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id, run_id=run_id, tool_outputs=tool_outputs
    )

def _dispatch_tools(tool_calls: List[Any]) -> List[Dict[str, str]]:
    outputs: List[Dict[str, str]] = []
    for call in tool_calls or []:
        call_id = _get(call, "id")
        name = _get(_get(call, "function", {}), "name")
        args_raw = _get(_get(call, "function", {}), "arguments", "{}")
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
        except json.JSONDecodeError:
            args = {"_raw": str(args_raw)}

        fn: Callable[..., Any] = TOOL_FUNCTIONS.get(name)
        if not fn:
            outputs.append({"tool_call_id": call_id, "output": json.dumps({"error": f"Unknown tool '{name}'"})})
            continue

        try:
            result = fn(**args) if isinstance(args, dict) else fn(args)
            outputs.append({"tool_call_id": call_id, "output": result if isinstance(result, str) else json.dumps(result)})
        except Exception as e:
            outputs.append({"tool_call_id": call_id, "output": json.dumps({"error": f"Tool '{name}' failed", "detail": str(e)})})
    return outputs

def _latest_assistant_text(thread_id: str) -> str:
    data = _get(_messages_list(thread_id), "data", []) or []
    for m in data:
        if _get(m, "role") == "assistant":
            t = extract_text_from_message(m).strip()
            if t:
                return t
    return ""

# ---------- main entry ----------
def run_assistant_conversation(
    user_text: str,
    thread_id: Optional[str] = None,
    instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns: {"reply": str, "thread_id": str, "meta": {...}}
    Never raises — callers can trust a friendly reply.
    """
    try:
        if not client or not OPENAI_API_KEY:
            return {
                "reply": "I couldn’t reach OpenAI because the API key isn’t loaded. Check OPENAI_API_KEY on the server.",
                "thread_id": thread_id or "",
                "meta": {"error": "missing_api_key"},
            }

        if not ASSISTANT_ID:
            return {
                "reply": "Your Assistant ID isn’t configured. Set PERSONAL_MENTOR_ASSISTANT_ID (or OPENAI_ASSISTANT_ID).",
                "thread_id": thread_id or "",
                "meta": {"error": "missing_assistant_id"},
            }

        t_id = thread_id or _threads_create()
        _message_create(t_id, "user", user_text)

        run = _run_create(t_id, ASSISTANT_ID, instructions or RUNTIME_INSTRUCTIONS)

        # Poll with tool handling
        start = time.time()
        max_wait_s = 120
        while True:
            cur = _run_retrieve(t_id, _get(run, "id"))
            status = _get(cur, "status")

            if status in ("queued", "in_progress"):
                if time.time() - start > max_wait_s:
                    return {
                        "reply": "This is taking longer than usual. Let’s try again in a moment.",
                        "thread_id": t_id,
                        "meta": {"timeout": True},
                    }
                time.sleep(0.6)
                continue

            if status == "requires_action":
                sto = _get(_get(cur, "required_action"), "submit_tool_outputs")
                tool_calls = _get(sto, "tool_calls") or []
                outputs = _dispatch_tools(tool_calls)
                _submit_tool_outputs(t_id, _get(run, "id"), outputs)
                time.sleep(0.3)
                continue

            if status in ("failed", "cancelled", "expired"):
                return {
                    "reply": "That run didn’t complete. Give me one more try or tweak your ask slightly.",
                    "thread_id": t_id,
                    "meta": {"status": status},
                }

            if status == "completed":
                break

            time.sleep(0.3)

        reply_text = _latest_assistant_text(t_id)
        if not reply_text or reply_text in PLACEHOLDERS:
            reply_text = (
                "I didn’t get a readable response there. Add one concrete detail (stack, feature, example) and I’ll get specific."
            )

        return {"reply": reply_text, "thread_id": t_id, "meta": {"ok": True}}

    except Exception as e:
        # Absolutely never raise out of here
        return {
            "reply": "The mentor hit an unexpected snag. Try again in a moment.",
            "thread_id": thread_id or "",
            "meta": {"error": "assistant.unexpected", "detail": str(e)},
        }
