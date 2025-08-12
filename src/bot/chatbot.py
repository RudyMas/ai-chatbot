from dataclasses import asdict
from .config import AppConfig

class Chatbot:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def whoami(self) -> str:
        c = self.cfg.chatbot.identity
        return f"I am {c.name} ({c.gender}, {c.age}), default language {c.language}."

    def summary(self) -> str:
        c = self.cfg.chatbot
        l = self.cfg.llm
        return (
            f"Name: {c.identity.name}\n"
            f"Personality: {c.personality.style} | Boundaries: {c.personality.boundaries}\n"
            f"LLM: {l.provider} / {l.model} (temp={l.temperature}, max_tokens={l.max_tokens})"
        )
