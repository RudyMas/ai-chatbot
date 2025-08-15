from dataclasses import dataclass, field
from typing import Dict, List, Tuple

@dataclass
class RuntimeState:
    tts_enabled: bool = False
    stt_enabled: bool = False
    active_profile: str = "default"

@dataclass
class SessionBuffer:
    """Holds recent turns for a session to enable periodic summaries."""
    turns: List[Tuple[str, str]] = field(default_factory=list)  # list of (role, text)
    count: int = 0
    # for debugging/transparency
    last_injected_notes: List[str] = field(default_factory=list)

state = RuntimeState()

# In-memory buffers per session name (web/API side)
session_buffers: Dict[str, SessionBuffer] = {}
