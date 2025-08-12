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
class UserConfig:
    name: str

@dataclass
class LLMConfig:
    provider: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    request_timeout: int

@dataclass
class AppConfig:
    chatbot: ChatbotConfig
    user: UserConfig
    llm: LLMConfig

def load_config(path: str | Path):
    cfg_path = Path(path)
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    cb = data["chatbot"]
    llm = data["llm"]
    user = data.get("user", {}) or {}

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

    user_cfg = UserConfig(name=user.get("name", "User"))

    llm_cfg = LLMConfig(
        provider=llm["provider"],
        base_url=llm.get("base_url", "http://localhost:11434"),
        model=llm["model"],
        temperature=float(llm["temperature"]),
        max_tokens=int(llm["max_tokens"]),
        request_timeout=int(llm.get("request_timeout", 60)),
    )

    return AppConfig(chatbot=chatbot, user=user_cfg, llm=llm_cfg), data

def get_system_template_path(cfg_file: Path, data: dict) -> Path:
    rel = data.get("prompt", {}).get("system_template", "src/bot/prompt/system_prompt.txt")
    base = cfg_file.parent.parent  # config/ -> repo root
    return (base / rel).resolve()
