from __future__ import annotations
import requests
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime

# Prefer stdlib zoneinfo if available (Py3.9+); otherwise fall back to naive time
try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from bot.config import AppConfig


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _resolve_timezone(cfg: AppConfig) -> str:
    """
    Read timezone from config at chatbot.identity.timezone.
    Falls back to 'Europe/Brussels' if not set.
    """
    try:
        tz = getattr(getattr(cfg.chatbot, "identity", None), "timezone", None)
        if tz:
            return str(tz)
    except Exception:
        pass
    return "Europe/Brussels"


def _now_string(tz_name: str) -> str:
    """
    Return a human-friendly "YYYY-MM-DD HH:MM (TZNAME)" timestamp.
    Uses zoneinfo if available; otherwise uses local naive time.
    """
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)
            return f"{now:%Y-%m-%d %H:%M} ({tz_name})"
        except Exception:
            pass  # fall through to naive
    now = datetime.now()
    return f"{now:%Y-%m-%d %H:%M} ({tz_name})"


def render_system_prompt(cfg: AppConfig, template_path: str) -> str:
    """
    Render your system template placeholders, then prefix a visible temporal header
    so the model reliably sees & uses the current time.
    Placeholders supported (as before):
      {{name}}, {{gender}}, {{age}}, {{language}}, {{style}}, {{boundaries}}, {{user_name}}
    """
    base = _read_text(template_path)
    ctx = {
        "name": cfg.chatbot.identity.name,
        "gender": cfg.chatbot.identity.gender,
        "age": str(cfg.chatbot.identity.age),
        "language": cfg.chatbot.identity.language,
        "style": cfg.chatbot.personality.style,
        "boundaries": cfg.chatbot.personality.boundaries,
        "user_name": cfg.user.name,
    }
    for k, v in ctx.items():
        base = base.replace(f"{{{{{k}}}}}", v)

    # Strong, top-of-prompt temporal header (models notice this better than an appendix)
    tz_name = _resolve_timezone(cfg)
    now_str = _now_string(tz_name)
    time_header = (
        "### Temporal context\n"
        f"Current date/time: {now_str}\n"
        "- Treat this as 'now' for any references to today/this week/etc.\n"
        "- If asked for the current time or date, use this value.\n"
        "- Do not say you cannot access the current time.\n\n"
    )

    return time_header + base.strip()


def _options(cfg: AppConfig) -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "temperature": cfg.llm.temperature,
        "num_predict": cfg.llm.max_tokens,
    }
    # optional context window if present in config
    if hasattr(cfg.llm, "num_ctx"):
        try:
            num_ctx = int(getattr(cfg.llm, "num_ctx"))
            if num_ctx > 0:
                opts["num_ctx"] = num_ctx
        except Exception:
            pass
    return opts


def generate(prompt: str, cfg: AppConfig, system_template_path: str) -> str:
    """Single-turn call (no history) via /api/generate."""
    system_text = render_system_prompt(cfg, system_template_path)
    url = cfg.llm.base_url.rstrip("/") + "/api/generate"
    payload: Dict[str, Any] = {
        "model": cfg.llm.model,
        "prompt": prompt,
        "system": system_text,
        "stream": False,
        "options": _options(cfg),
    }
    r = requests.post(url, json=payload, timeout=cfg.llm.request_timeout)
    if not r.ok:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        raise RuntimeError(f"Ollama error {r.status_code}: {err}")
    data = r.json()
    return (data.get("response") or "").strip()


def generate_chat(history: List[Tuple[str, str]], user_message: str, cfg: AppConfig, system_template_path: str) -> str:
    """
    Multi-turn call via /api/chat.
    history: list of (role, text) where role in {'user','assistant'}
    user_message: the new user input (already augmented with RAG notes if any)
    """
    system_text = render_system_prompt(cfg, system_template_path)
    url = cfg.llm.base_url.rstrip("/") + "/api/chat"

    messages = [{"role": "system", "content": system_text}]
    for role, text in history:
        role = "user" if role.lower().startswith("user") else "assistant"
        messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_message})

    payload: Dict[str, Any] = {
        "model": cfg.llm.model,
        "messages": messages,
        "stream": False,
        "options": _options(cfg),
    }
    r = requests.post(url, json=payload, timeout=cfg.llm.request_timeout)
    if not r.ok:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        raise RuntimeError(f"Ollama error {r.status_code}: {err}")
    data = r.json()
    # /api/chat returns {"message":{"role":"assistant","content":"..."},"done":true,...}
    msg = data.get("message") or {}
    return (msg.get("content") or "").strip()
