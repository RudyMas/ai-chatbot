from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class ChatbotIdentity:
    name: str
    gender: str
    age: int
    language: str

@dataclass
class ChatbotPersonality:
    style: str
    boundaries: str

@dataclass
class ChatbotConfig:
    identity: ChatbotIdentity
    personality: ChatbotPersonality

@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float
    max_tokens: int

@dataclass
class AppConfig:
    chatbot: ChatbotConfig
    llm: LLMConfig

def load_config(path: str | Path) -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    cb = data["chatbot"]
    llm = data["llm"]

    identity = ChatbotIdentity(
        name=cb["name"],
        gender=cb["identity"]["gender"],
        age=int(cb["identity"]["age"]),
        language=cb["identity"]["language"],
    )
    personality = ChatbotPersonality(
        style=cb["personality"]["style"],
        boundaries=cb["personality"]["boundaries"],
    )
    chatbot = ChatbotConfig(identity=identity, personality=personality)
    llm_cfg = LLMConfig(
        provider=llm["provider"],
        model=llm["model"],
        temperature=float(llm["temperature"]),
        max_tokens=int(llm["max_tokens"]),
    )
    return AppConfig(chatbot=chatbot, llm=llm_cfg)
