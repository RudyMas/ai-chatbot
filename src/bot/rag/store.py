from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime
from typing import List, Dict, Any

class RAGStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, entry: Dict[str, Any]) -> None:
        entry = {
            **entry,
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def make_summary_entry(session: str, user_name: str, text: str, tags: List[str]) -> Dict[str, Any]:
        return {
            "id": f"{session}-{int(datetime.utcnow().timestamp())}",
            "type": "note",
            "session": session,
            "user_name": user_name,
            "tags": tags,
            "text": text.strip(),
        }

    @staticmethod
    def make_fact_entry(session: str, user_name: str, text: str, tags: List[str]) -> Dict[str, Any]:
        return {
            "id": f"{session}-fact-{int(datetime.utcnow().timestamp())}",
            "type": "fact",
            "session": session,
            "user_name": user_name,
            "tags": tags,
            "text": text.strip(),
        }
