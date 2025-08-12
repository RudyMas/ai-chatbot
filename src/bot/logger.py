from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from typing import Optional

@dataclass
class LogConfig:
    directory: Path
    session_prefix: str = "chat"
    fmt: str = "jsonl"  # reserved for future formats

class TranscriptLogger:
    def __init__(self, cfg: LogConfig, session_name: Optional[str] = None):
        self.cfg = cfg
        self.cfg.directory.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{cfg.session_prefix}-{session_name or ts}"
        self.path = self.cfg.directory / f"{base}.jsonl"

        # Write a tiny header line
        header = {
            "type": "session",
            "ts": datetime.now().isoformat(timespec="seconds"),
            "meta": {"name": session_name or ts}
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(header, ensure_ascii=False) + "\n")

    def log(self, role: str, text: str):
        rec = {
            "type": "message",
            "ts": datetime.now().isoformat(timespec="seconds"),
            "role": role,
            "text": text
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
