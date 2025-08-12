from __future__ import annotations
import requests
from pathlib import Path
from typing import Dict, Any
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

def generate(prompt: str, cfg: AppConfig, system_template_path: str) -> str:
    system_text = render_system_prompt(cfg, system_template_path)
    url = cfg.llm.base_url.rstrip("/") + "/api/generate"

    payload: Dict[str, Any] = {
        "model": cfg.llm.model,
        "prompt": prompt,
        "system": system_text,
        "stream": False,
        "options": {
            "temperature": cfg.llm.temperature,
            "num_predict": cfg.llm.max_tokens
        }
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
