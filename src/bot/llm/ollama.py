from __future__ import annotations
import requests
from pathlib import Path
from dataclasses import asdict
from typing import Dict, Any
from bot.config import AppConfig

def render_system_prompt(cfg: AppConfig, template_path: str) -> str:
    # super small templater using str.replace; keeps deps minimal
    t = Path(template_path).read_text(encoding="utf-8")
    ctx = {
        "name": cfg.chatbot.identity.name,
        "gender": cfg.chatbot.identity.gender,
        "age": str(cfg.chatbot.identity.age),
        "language": cfg.chatbot.identity.language,
        "style": cfg.chatbot.personality.style,
        "boundaries": cfg.chatbot.personality.boundaries,
    }
    for k, v in ctx.items():
        t = t.replace(f"{{{{{k}}}}}", v)
    return t

def generate(prompt: str, cfg: AppConfig) -> str:
    assert cfg.llm.provider == "ollama", "Only 'ollama' is supported in step 2."
    system_path = cfg.prompt_system_path  # set by a tiny helper below

    system_text = render_system_prompt(cfg, system_path)
    url = cfg.llm_base_url.rstrip("/") + "/api/generate"

    payload: Dict[str, Any] = {
        "model": cfg.llm.model,
        "prompt": prompt,
        "system": system_text,
        "options": {
            "temperature": cfg.llm.temperature,
            "num_predict": cfg.llm.max_tokens
        }
    }
    r = requests.post(url, json=payload, timeout=cfg.llm_request_timeout)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "").strip()

# small accessors so we don't change your dataclasses yet
def bind_cfg_helpers(cfg: AppConfig, system_template_path: str):
    # attach a few convenience properties dynamically (keeps step 2 small)
    setattr(cfg, "llm_base_url", cfg.llm.provider and cfg.llm.__dict__.get("base_url", None) or None)
    if getattr(cfg, "llm_base_url", None) is None:
        # fallback to config dict if dataclass didn’t include base_url yet
        pass
    setattr(cfg, "llm_request_timeout", cfg.llm.__dict__.get("request_timeout", 60))
    setattr(cfg, "prompt_system_path", system_template_path)
