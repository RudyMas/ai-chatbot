from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot.config import load_config, get_system_template_path, UserConfig
from bot.llm.ollama import generate_chat
from bot.logger import TranscriptLogger, LogConfig
from bot.rag.store import RAGStore
from bot.rag.retriever import SimpleRetriever
from bot.rag.summarizer import summarize_chunk
from server.state import state, session_buffers, SessionBuffer

# ---------- App bootstrap ----------
ROOT = Path(__file__).parents[2]
CFG_PATH = ROOT / "config" / "default.yaml"

app = FastAPI()

# serve web/ directory for static files
WEB_DIR = ROOT / "web"
WEB_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# Load config & setup
app_cfg, raw_cfg = load_config(CFG_PATH)
TEMPLATE_PATH = get_system_template_path(CFG_PATH, raw_cfg)

# logging setup
logs_dir = raw_cfg.get("logging", {}).get("dir", "logs")
prefix = raw_cfg.get("logging", {}).get("session_prefix", "chat")
LOG_DIR = ROOT / logs_dir
LOG_DIR.mkdir(parents=True, exist_ok=True)

# rag setup
rag_cfg = raw_cfg.get("rag", {}) if isinstance(raw_cfg, dict) else {}
store_path = rag_cfg.get("store_path", "data/rag/store.jsonl")
STORE = RAGStore(ROOT / store_path)

# chat settings
chat_cfg = raw_cfg.get("chat", {}) if isinstance(raw_cfg, dict) else {}
history_max_messages = int(chat_cfg.get("history_max_messages", 8))

# ---------- Models ----------
class ChatIn(BaseModel):
    message: str
    user: Optional[str] = None
    session: Optional[str] = None

class ChatOut(BaseModel):
    answer: str
    model: str
    tts_enabled: bool
    stt_enabled: bool

class RememberIn(BaseModel):
    text: str
    tags: Optional[List[str]] = None
    user: Optional[str] = None
    session: Optional[str] = None

class ToggleIn(BaseModel):
    tts: Optional[bool] = None
    stt: Optional[bool] = None

# ---------- Helpers ----------
def _build_logger(session_name: Optional[str], user_name: str | None):
    log_cfg = LogConfig(directory=LOG_DIR, session_prefix=prefix)
    return TranscriptLogger(log_cfg, session_name=session_name, user_name=user_name or "User")

def _extract_tags_from_text(text: str) -> List[str]:
    tags: List[str] = []
    i = 0
    while i < len(text):
        if text[i] == "#":
            j = i + 1
            token = []
            while j < len(text) and (text[j].isalnum() or text[j] in ("-", "_")):
                token.append(text[j])
                j += 1
            if token:
                tags.append("".join(token).lower())
            i = j
        else:
            i += 1
    # dedupe while preserving order
    out: List[str] = []
    for t in tags:
        if t not in out:
            out.append(t)
    return out

def _strip_hashtags(text: str) -> str:
    return " ".join(p for p in text.split() if not (p.startswith("#") and len(p) > 1)).strip()

def _context_block(notes: list[str]) -> str:
    if not notes:
        return ""
    return "Relevant notes:\n" + "\n".join(f"- {n}" for n in notes) + "\n\n"

def _build_retriever(user_name: Optional[str]):
    require_user_match = bool(rag_cfg.get("require_user_match", False))
    retr = SimpleRetriever(
        store_path=ROOT / store_path,
        require_tags=rag_cfg.get("require_tags", []),
        user_name=user_name,
        require_user_match=require_user_match,
        global_tags=rag_cfg.get("global_tags", []),
    )
    top_k = int(rag_cfg.get("top_k", 3))
    max_note_words = int(rag_cfg.get("max_note_words", 60))
    return retr, top_k, max_note_words

def _get_session_buffer(name: str) -> SessionBuffer:
    if name not in session_buffers:
        session_buffers[name] = SessionBuffer()
    return session_buffers[name]

# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8") if (WEB_DIR / "index.html").exists() \
        else "<h1>LocalAI Bot</h1><p>Place web/index.html to use the UI.</p>"
    return HTMLResponse(html)

@app.post("/chat", response_model=ChatOut)
def chat(inp: ChatIn):
    user_name = (inp.user or raw_cfg.get("user", {}).get("name") or "User").strip()
    sess = (inp.session or "api").strip()

    # Put username into persona context
    app_cfg.user = UserConfig(name=user_name)

    # Retrieve RAG notes (user-scoped with optional global)
    notes = []
    if rag_cfg.get("enabled", True):
        retr, top_k, max_note_words = _build_retriever(user_name)
        notes = retr.top_k_notes(inp.message, top_k, max_note_words)
    user_line = f"{user_name}: {inp.message}"
    final_user = _context_block(notes) + user_line

    # Logger
    logger = _build_logger(sess, user_name)
    logger.log("user", inp.message, user_name=user_name)

    # Session history
    buf = _get_session_buffer(sess)
    buf.turns.append(("user", user_line))
    buf.count += 1

    # Use chat history with bounded context
    history_slice = buf.turns[-history_max_messages:] if history_max_messages > 0 else buf.turns
    try:
        answer = generate_chat(history_slice, final_user, app_cfg, str(TEMPLATE_PATH))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.log("assistant", answer)
    buf.turns.append(("assistant", answer))
    buf.count += 1

    # Periodic summaries → saved to RAG store (scoped to this user)
    if rag_cfg.get("enabled", True):
        chunk_messages = int(rag_cfg.get("chunk_messages", 6))
        max_words = int(rag_cfg.get("summary_max_words", 120))
        tags = list(rag_cfg.get("tags", ["session-summary"]))
        if chunk_messages > 0 and (buf.count % chunk_messages == 0):
            recent = buf.turns[-chunk_messages:]
            note = summarize_chunk(app_cfg, str(TEMPLATE_PATH), recent, max_words)
            entry = RAGStore.make_summary_entry(sess, user_name, note, tags)
            STORE.append(entry)

    return ChatOut(
        answer=answer,
        model=app_cfg.llm.model,
        tts_enabled=state.tts_enabled,
        stt_enabled=state.stt_enabled
    )

@app.post("/remember")
def remember(inp: RememberIn):
    user_name = (inp.user or raw_cfg.get("user", {}).get("name") or "User").strip()
    text = inp.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    tags = inp.tags or _extract_tags_from_text(text)
    clean = _strip_hashtags(text)
    entry = RAGStore.make_fact_entry(inp.session or "api", user_name, clean, ["manual"] + tags)
    STORE.append(entry)
    return {"ok": True, "stored": {"user_name": user_name, "text": clean, "tags": ["manual"] + tags}}

@app.post("/toggle")
def toggle(inp: ToggleIn):
    if inp.tts is not None:
        state.tts_enabled = bool(inp.tts)
    if inp.stt is not None:
        state.stt_enabled = bool(inp.stt)
    return {"tts_enabled": state.tts_enabled, "stt_enabled": state.stt_enabled}
