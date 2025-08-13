from dataclasses import dataclass, field
from typing import Dict, List, Tuple

@dataclass
class RuntimeState:
    tts_enabled: bool = False
    stt_enabled: bool = False

@dataclass
class SessionBuffer:
    """Holds recent turns for a session to enable periodic summaries."""
    turns: List[Tuple[str, str]] = field(default_factory=list)  # list of (role, text)
    count: int = 0

state = RuntimeState()

# In-memory buffers per session name
session_buffers: Dict[str, SessionBuffer] = {}
