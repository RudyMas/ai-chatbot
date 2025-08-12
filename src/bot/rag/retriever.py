from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Iterable, Optional
import json
import re

_BASIC_STOPWORDS = {
    "the","a","an","and","or","but","if","on","in","at","to","for","of","with","by",
    "is","are","was","were","be","been","being","this","that","it","as","from","about",
    "you","your","i","we","they","he","she","them","us","our","my","me"
}

def _tokens(s: str) -> List[str]:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if t and t not in _BASIC_STOPWORDS]
    return toks

def _score(query: str, text: str) -> float:
    """Very light keyword overlap score with length normalization."""
    q = set(_tokens(query))
    if not q:
        return 0.0
    t = _tokens(text)
    if not t:
        return 0.0
    overlap = sum(1 for w in t if w in q)
    return overlap / (len(t) ** 0.5)

def _trim_words(text: str, max_words: int) -> str:
    ws = text.strip().split()
    if len(ws) <= max_words:
        return text.strip()
    return " ".join(ws[:max_words]) + " …"

class SimpleRetriever:
    def __init__(
        self,
        store_path: str | Path,
        require_tags: Iterable[str] | None = None,
        user_name: Optional[str] = None,
        require_user_match: bool = False,
        global_tags: Iterable[str] | None = None,
    ):
        self.path = Path(store_path)
        self.require_tags = set(require_tags or [])
        self.user_name = user_name
        self.require_user_match = require_user_match
        self.global_tags = set(global_tags or [])
        self.docs: List[Dict] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        self.docs.clear()
        if not self.path.exists():
            self._loaded = True
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # tag filter
                if self.require_tags:
                    tags = set(obj.get("tags", []))
                    if not self.require_tags.issubset(tags):
                        continue
                # user scoping
                if self.require_user_match:
                    note_user = (obj.get("user_name") or "").strip()
                    tags = set(obj.get("tags", []))
                    is_global = bool(self.global_tags and (self.global_tags & tags))
                    if not is_global:
                        if not self.user_name:
                            # if we require match but don't know the user, skip
                            continue
                        if note_user.lower() != self.user_name.lower():
                            continue
                if "text" in obj:
                    self.docs.append(obj)
        self._loaded = True

    def top_k_notes(self, query: str, k: int, max_note_words: int) -> List[str]:
        self._load()
        if not self.docs or not query.strip():
            return []
        scored = [( _score(query, d["text"]), d["text"] ) for d in self.docs]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sc, txt in scored[:k]:
            if sc <= 0:
                break
            out.append(_trim_words(txt, max_note_words))
        return out
