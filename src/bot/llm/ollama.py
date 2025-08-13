from __future__ import annotations
import requests
from pathlib import Path
from typing import Dict, Any, List, Tuple
from bot.config import AppConfig

def render_system_prompt(cfg: AppConfig, template_path: str) -> str:
    t = Path(template_path).read_text(encoding="utf-8")
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
        t = t.replace(f"{{{{{k}}}}}", v)
    return t

def _options(cfg: AppConfig) -> Dict[str, Any]:
    opts = {
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
