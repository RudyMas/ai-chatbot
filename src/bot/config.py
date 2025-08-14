from dataclasses import dataclass
from pathlib import Path
from typing import Optional
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
    # Optional: pass larger context window to Ollama if supported by the model
    num_ctx: Optional[int] = None

@dataclass
class AppConfig:
    chatbot: ChatbotConfig
    user: UserConfig
    llm: LLMConfig

def load_config(path: str | Path):
    cfg_path = Path(path).resolve()
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
        num_ctx=int(llm.get("num_ctx")) if llm.get("num_ctx") is not None else None,
    )

    return AppConfig(chatbot=chatbot, user=user_cfg, llm=llm_cfg), data

def _detect_repo_root(start: Path) -> Path:
    """
    Walk up from `start` to find the project root.
    Heuristics: directory containing 'src' or 'pyproject.toml'.
    Falls back to the parent of 'config' if present, else start.parent.
    """
    cur = start
    for _ in range(8):  # climb up a few levels safely
        if (cur / "src").exists() or (cur / "pyproject.toml").exists():
            return cur
        if cur.name.lower() == "config" and cur.parent.exists():
            # likely .../<repo>/config; prefer the parent as root
            return cur.parent
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.parent

def get_system_template_path(cfg_file: Path, data: dict) -> Path:
    """
    Resolve prompt.system_template robustly:
      - If absolute: return as-is.
      - If relative: treat it as relative to the project root (not config/).
    """
    raw = data.get("prompt", {}).get("system_template", "src/bot/prompt/system_prompt.txt")
    p = Path(raw)
    if p.is_absolute():
        return p

    # Find repo root starting from the config file location
    repo_root = _detect_repo_root(Path(cfg_file).resolve().parent)
    return (repo_root / p).resolve()
