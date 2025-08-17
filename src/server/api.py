from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import io
import os
import json
import uuid
import tempfile
import subprocess

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Body
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from bot.llm.ollama import get_last_ollama_payload
from bot.llm.ollama import generate  # single-shot generator

from bot.config import load_config, get_system_template_path, UserConfig
from bot.llm.ollama import generate_chat
from bot.logger import TranscriptLogger, LogConfig
from bot.rag.store import RAGStore
from bot.rag.retriever import SimpleRetriever
from bot.rag.summarizer import summarize_chunk
from server.state import state, session_buffers, SessionBuffer

# ---------- App bootstrap ----------
ROOT = Path(__file__).parents[2]
app = FastAPI()

# serve web/
WEB_DIR = ROOT / "web"
WEB_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# global mutable config (load default profile at boot)
from bot.profiles import load_profile, list_profiles

app_cfg, raw_cfg, TEMPLATE_PATH = load_profile(state.active_profile)


def _setup_dirs():
    logs_dir = raw_cfg.get("logging", {}).get("dir", "logs")
    log_dir = ROOT / logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    rag_cfg = raw_cfg.get("rag", {}) if isinstance(raw_cfg, dict) else {}
    store_path = rag_cfg.get("store_path", "data/rag/store.jsonl")
    store = RAGStore(ROOT / store_path)

    chat_cfg = raw_cfg.get("chat", {}) if isinstance(raw_cfg, dict) else {}
    history_max = int(chat_cfg.get("history_max_messages", 8))

    prefix = raw_cfg.get("logging", {}).get("session_prefix", "chat")
    return log_dir, store, rag_cfg, history_max, prefix


def _hydrate_audio_flags_from_config():
    # Read audio.tts.enabled and audio.stt.enabled into runtime state
    audio = (raw_cfg.get("audio") or {}) if isinstance(raw_cfg, dict) else {}
    tts = (audio.get("tts") or {})
    stt = (audio.get("stt") or {})
    state.tts_enabled = bool(tts.get("enabled", False))
    state.stt_enabled = bool(stt.get("enabled", False))


LOG_DIR, STORE, rag_cfg, history_max_messages, LOG_PREFIX = _setup_dirs()
_hydrate_audio_flags_from_config()


# ---------- Models ----------
class ChatIn(BaseModel):
    message: str
    user: Optional[str] = None
    session: Optional[str] = None
    # NEW: when true, store user text in short-term buffer (and RAG)
    # without calling the LLM or speaking back
    listen_only: Optional[bool] = None
    # Optional tags for RAG fact when listen_only is used
    remember_tags: Optional[List[str]] = None


class ChatOut(BaseModel):
    answer: str
    model: str
    tts_enabled: bool
    stt_enabled: bool
    profile: str


class RememberIn(BaseModel):
    text: str
    tags: Optional[List[str]] = None
    user: Optional[str] = None
    session: Optional[str] = None


class ToggleIn(BaseModel):
    tts: Optional[bool] = None
    stt: Optional[bool] = None


class ProfileSelectIn(BaseModel):
    profile: str


class MemoryListOut(BaseModel):
    total: int
    items: list


class MemoryDeleteIn(BaseModel):
    idx: List[int]  # line numbers to delete


class MemoryFlushIn(BaseModel):
    user: Optional[str] = None
    session: Optional[str] = None


class MemoryCleanIn(BaseModel):
    user: Optional[str] = None
    # If provided, keep only the most recent N items for this user (after dedup)
    keep_latest: Optional[int] = None


class DemoIn(BaseModel):
    user: Optional[str] = None
    session: Optional[str] = None
    demo_mode: Optional[bool] = None


# ---------- Helpers ----------
def _build_logger(session_name: Optional[str], user_name: str | None):
    log_cfg = LogConfig(directory=LOG_DIR, session_prefix=LOG_PREFIX)
    return TranscriptLogger(log_cfg, session_name=session_name, user_name=user_name or "User")


def _extract_tags_from_text(text: str) -> List[str]:
    tags: List[str] = []
    i = 0
    while i < len(text):
        if text[i] == "#":
            j = i + 1
            token: List[str] = []
            while j < len(text) and (text[j].isalnum() or text[j] in ("-", "_")):
                token.append(text[j])
                j += 1
            if token:
                tags.append("".join(token).lower())
            i = j
        else:
            i += 1
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
        store_path=STORE.path,
        require_tags=rag_cfg.get("require_tags", []),
        user_name=user_name,
        require_user_match=require_user_match,
        global_tags=rag_cfg.get("global_tags", []),
    )
    top_k = int(rag_cfg.get("top_k", 3))
    max_note_words = int(rag_cfg.get("max_note_words", 60))
    min_score = float(rag_cfg.get("min_score", 0.0))
    fallback_recent = int(rag_cfg.get("fallback_recent", 0))
    return retr, top_k, max_note_words, min_score, fallback_recent


def _get_session_buffer(name: str) -> SessionBuffer:
    if name not in session_buffers:
        session_buffers[name] = SessionBuffer()
    return session_buffers[name]


def _audio_cfg():
    audio = (raw_cfg.get("audio") or {}) if isinstance(raw_cfg, dict) else {}
    tts = (audio.get("tts") or {})
    stt = (audio.get("stt") or {})
    return tts, stt


def _reload_profile(profile: str):
    global app_cfg, raw_cfg, TEMPLATE_PATH, LOG_DIR, STORE, rag_cfg, history_max_messages, LOG_PREFIX
    app_cfg, raw_cfg, TEMPLATE_PATH = load_profile(profile)
    LOG_DIR, STORE, rag_cfg, history_max_messages, LOG_PREFIX = _setup_dirs()
    _hydrate_audio_flags_from_config()
    state.active_profile = profile
    session_buffers.clear()


def _read_store_all() -> List[Dict[str, Any]]:
    """Read the entire JSONL store into memory as a list of dicts."""
    path = STORE.path
    entries: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    # skip malformed lines
                    continue
    except FileNotFoundError:
        pass
    return entries


def _write_store_all(entries: List[Dict[str, Any]]) -> None:
    """Rewrite the JSONL file with the given entries."""
    path = STORE.path
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _normalize_text(t: str) -> str:
    return " ".join((t or "").strip().lower().split())


def _matches_filters(
        e: Dict[str, Any],
        user: Optional[str],
        session: Optional[str],
        tags: Optional[List[str]],
        types: Optional[List[str]],
) -> bool:
    if user and e.get("user_name") != user:
        return False
    if session and e.get("session") != session:
        return False
    if types:
        if (e.get("type") or "").lower() not in {t.lower() for t in types}:
            return False
    if tags:
        etags = [str(t).lower() for t in (e.get("tags") or [])]
        for t in tags:
            if t.lower() not in etags:
                return False
    return True


# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8") if (WEB_DIR / "index.html").exists() \
        else "<h1>LocalAI Bot</h1><p>Place web/index.html to use the UI.</p>"
    return HTMLResponse(html)


@app.get("/profiles")
def get_profiles():
    return {"active": state.active_profile, "profiles": ["default"] + list_profiles()}


@app.post("/profile/select")
def select_profile(inp: ProfileSelectIn):
    try:
        _reload_profile(inp.profile)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "active": state.active_profile}


@app.post("/chat", response_model=ChatOut)
def chat(inp: ChatIn):
    user_name = (inp.user or raw_cfg.get("user", {}).get("name") or "User").strip()
    sess = (inp.session or "api").strip()
    app_cfg.user = UserConfig(name=user_name)

    # Handle /flush commands before any LLM call
    low = inp.message.strip().lower()
    if low.startswith("/flush"):
        buf = _get_session_buffer(sess)
        if not buf.turns:
            text = "Nothing to flush."
        else:
            all_flag = (low == "/flush all")
            window = buf.turns[:] if all_flag else buf.turns[-(rag_cfg.get("chunk_messages", 6) or len(buf.turns)):]
            note = summarize_chunk(app_cfg, str(TEMPLATE_PATH), window, int(rag_cfg.get("summary_max_words", 120)))
            entry = RAGStore.make_summary_entry(sess, user_name, note, list(rag_cfg.get("tags", ["session-summary"])))
            STORE.append(entry)
            flushed = len(window)
            buf.turns.clear()
            buf.count = 0
            text = f"✓ Flushed {flushed} turns to RAG and cleared buffer."
        return ChatOut(answer=text, model=app_cfg.llm.model, tts_enabled=state.tts_enabled,
                       stt_enabled=state.stt_enabled, profile=state.active_profile)

    # --- Listen-only mode: store to buffer (+optional RAG) without LLM ---
    if inp.listen_only:
        logger = _build_logger(sess, user_name)
        logger.log("user", inp.message, user_name=user_name)

        # Append to the session buffer (short-term memory)
        buf = _get_session_buffer(sess)
        user_line = f"{user_name}: {inp.message}"
        buf.turns.append(("user", user_line))
        buf.count += 1

        # Optionally store to RAG as a fact (mirror previous /remember behavior)
        if rag_cfg.get("enabled", True):
            try:
                tags = list(dict.fromkeys((inp.remember_tags or []) + ["voice", "viewer"]))
                entry = RAGStore.make_fact_entry(sess, user_name, inp.message, tags)
                STORE.append(entry)
            except Exception:
                pass  # non-fatal

            # Keep periodic auto-summary behavior
            chunk_messages = int(rag_cfg.get("chunk_messages", 6))
            max_words = int(rag_cfg.get("summary_max_words", 120))
            tags_sum = list(rag_cfg.get("tags", ["session-summary"]))
            if chunk_messages > 0 and (buf.count % chunk_messages == 0):
                recent = buf.turns[-chunk_messages:]
                note = summarize_chunk(app_cfg, str(TEMPLATE_PATH), recent, max_words)
                entry = RAGStore.make_summary_entry(sess, user_name, note, tags_sum)
                STORE.append(entry)

        # Return a neutral response; UI won’t TTS this
        return ChatOut(
            answer="(muted) stored.",
            model=app_cfg.llm.model,
            tts_enabled=state.tts_enabled,
            stt_enabled=state.stt_enabled,
            profile=state.active_profile
        )

    # Normal chat flow
    notes: List[str] = []
    if rag_cfg.get("enabled", True):
        retr, top_k, max_note_words, min_score, fallback_recent = _build_retriever(user_name)
        notes = retr.top_k_notes(inp.message, top_k, max_note_words, min_score=min_score,
                                 fallback_recent=fallback_recent)

    user_line = f"{user_name}: {inp.message}"
    final_user = _context_block(notes) + user_line

    logger = _build_logger(sess, user_name)
    logger.log("user", inp.message, user_name=user_name)

    buf = _get_session_buffer(sess)
    buf.turns.append(("user", user_line))
    buf.count += 1
    buf.last_injected_notes = notes[:]  # for /debug/context

    history_slice = buf.turns[-history_max_messages:] if history_max_messages > 0 else buf.turns
    try:
        answer = generate_chat(history_slice, final_user, app_cfg, str(TEMPLATE_PATH))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.log("assistant", answer)
    buf.turns.append(("assistant", answer))
    buf.count += 1

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
        stt_enabled=state.stt_enabled,
        profile=state.active_profile
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


# ---------- New: TTS ----------
from typing import Optional
from fastapi import Query, Body, Form


@app.api_route("/speak", methods=["GET", "POST"])
def speak(
        text: Optional[str] = Query(None),
        text_body: Optional[str] = Body(None),
        text_form: Optional[str] = Form(None),
):
    """
    TTS using Piper. Accepts text via query (?text=...), JSON body {"text": "..."} or form field.
    Returns a WAV file. Provides clearer error messages on failure.
    """
    # Pick the first non-empty source
    txt = (text_body or text_form or text or "").strip()
    if not txt:
        raise HTTPException(status_code=400, detail="Missing 'text' (query, JSON body, or form).")

    # (Optional) Cap extremely long inputs to avoid piper misbehavior on huge paragraphs
    if len(txt) > 4000:
        txt = txt[:4000] + " …"

    # pull audio config
    tts_cfg, _ = _audio_cfg()
    voice = tts_cfg.get("voice", "en_US-lessac-medium")
    model_dir = tts_cfg.get("model_dir", "./data/piper")
    sr = int(tts_cfg.get("sample_rate", 22050))

    model_path = os.path.join(model_dir, f"{voice}.onnx")
    config_path = os.path.join(model_dir, f"{voice}.onnx.json")

    if not os.path.exists(model_path):
        raise HTTPException(status_code=500, detail=f"Piper model not found: {model_path}")
    if not os.path.exists(config_path):
        raise HTTPException(status_code=500, detail=f"Piper config not found: {config_path}")

    piper_bin = "piper.exe" if os.name == "nt" else "piper"
    tmp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.wav")

    try:
        # Feed text on stdin
        proc = subprocess.run(
            [piper_bin, "--model", model_path, "--config", config_path, "--output_file", tmp_wav, "--sample_rate",
             str(sr)],
            input=txt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,  # we'll handle returncode ourselves for better messages
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "ignore").strip()
            raise HTTPException(status_code=500, detail=f"Piper failed (code {proc.returncode}): {err[:800]}")

        if not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) == 0:
            raise HTTPException(status_code=500, detail="Piper produced no audio (empty file).")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Piper binary not found on PATH (piper/piper.exe).")
    except HTTPException:
        # re-raise our detailed messages
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")

    return FileResponse(tmp_wav, media_type="audio/wav", filename="speech.wav")


# ---------- New: STT ----------
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not state.stt_enabled:
        raise HTTPException(status_code=503, detail="STT disabled")

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        raise HTTPException(status_code=500, detail="faster-whisper not installed")

    _, stt_cfg = _audio_cfg()
    model_size = stt_cfg.get("model_size", "base")
    device = (stt_cfg.get("device") or "cpu").lower()  # "cpu" or "cuda"
    compute_type = "int8" if device == "cpu" else "int8_float16"

    # Save temp file
    tmp_path = os.path.join(tempfile.gettempdir(), f"stt_{uuid.uuid4().hex}_{file.filename or 'audio'}")
    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    def _run_transcribe(vad: bool):
        model = WhisperModel(model_size, device=device, compute_type=compute_type, num_workers=1)
        segments, info = model.transcribe(
            tmp_path,
            vad_filter=vad,
            # slightly more permissive defaults
            beam_size=1,
            best_of=1,
        )
        parts = [seg.text.strip() for seg in segments if getattr(seg, "text", "").strip()]
        text = " ".join(p for p in parts if p)
        return text, getattr(info, "language", None)

    try:
        # 1st pass with VAD filter
        text, lang = _run_transcribe(vad=True)

        # 2nd pass fallback without VAD if nothing recognized
        if not text:
            text, lang = _run_transcribe(vad=False)

        return {"text": text or "", "language": lang, "device": device}
    except Exception as e:
        msg = str(e)
        if "cudnn" in msg.lower():
            msg += " (Tip: set audio.stt.device: 'cpu' in config or install CUDA/cuDNN to use GPU.)"
        raise HTTPException(status_code=500, detail=f"STT error: {msg}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


@app.post("/demo/set")
def demo_set(inp: DemoIn):
    """
    Toggle demo_mode server-side (optional convenience).
    """
    if inp.demo_mode is not None:
        state.demo_mode = bool(inp.demo_mode)
    return {"ok": True, "demo_mode": getattr(state, "demo_mode", False)}


@app.post("/demo/speak")
def demo_speak(inp: DemoIn):
    """
    Generate a short, witty, 1–2 sentence remark based on recent context
    (short-term buffer) — perfect for a mic-drop at the end of a talk.
    """
    user_name = (inp.user or raw_cfg.get("user", {}).get("name") or "User").strip()
    sess = (inp.session or "api").strip()

    # pull recent turns from the in-memory session buffer
    buf = _get_session_buffer(sess)
    recent = buf.turns[-history_max_messages:] if history_max_messages > 0 else buf.turns[:]

    # Build a compact transcript block (keep it lean)
    lines = []
    for role, text in recent[-18:]:  # last ~18 lines max
        # strip any 'Relevant notes:' lines and keep pure dialogue
        if role == "assistant":
            lines.append(f"Assistant: {text.strip()}")
        else:
            # history stores e.g. "Rudy: hi", keep as-is
            lines.append(text.strip())

    transcript = "\n".join(lines).strip()
    print(f"Transcript for demo remark:\n{transcript}\n")

    # show transcript
    if not transcript:
        raise HTTPException(status_code=400, detail="No recent conversation history to base remark on.")
    if len(transcript) > 2000:
        # truncate to avoid too long prompts
        transcript = transcript[:2000] + " … (truncated)"
    if not transcript.endswith("."):
        transcript += "."
    # Ensure we have a newline at the end for better formatting
    if not transcript.endswith("\n"):
        transcript += "\n"
    # If the transcript is too short, we can't generate a meaningful remark
    if len(transcript) < 20:
        raise HTTPException(status_code=400, detail="Transcript too short for a meaningful remark.")
    # Ensure we have a newline at the end for better formatting

    # show the transcript on screen
    print(f"Transcript for demo remark:\n{transcript}\n")

    # Compose a targeted single-turn prompt
    prompt = (
        "You are about to make a single short remark for the audience.\n"
        "Constraints:\n"
        "- 1–2 sentences max\n"
        "- Polished, lightly witty\n"
        "- React to themes in the transcript; do NOT quote it verbatim\n"
        "- No meta talk about being an AI or time access\n"
        "- Be helpful and relevant; include a subtle callback if natural\n\n"
        f"Transcript (recent):\n{transcript}\n\n"
        "Your remark:"
    )

    try:
        # single-turn call (no history): we still use the same system prompt/persona
        answer = generate(prompt, app_cfg, str(TEMPLATE_PATH))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo speak error: {e}")

    # Log like a normal assistant turn so UI panels show it
    logger = _build_logger(sess, user_name)
    logger.log("assistant", answer)
    buf.turns.append(("assistant", answer))
    buf.count += 1

    return {"ok": True, "answer": answer, "profile": state.active_profile}


# ---------- New: Debug ----------
@app.get("/debug/context")
def debug_context(session: Optional[str] = None, user: Optional[str] = None, rag_last: int = 20):
    """
    Show exactly what the server sees for this user/session:
    - Current profile
    - User name
    - Session name
    - Short-term buffer (turns in memory)
    - Last injected RAG notes
    - Identity language from YAML config
    - Identity name from YAML config
    """
    sess = (session or "api").strip()
    user_name = (user or raw_cfg.get("user", {}).get("name") or "User").strip()

    buf = _get_session_buffer(sess)

    identity_name = getattr(getattr(app_cfg, "chatbot", None), "name", None) \
                    or raw_cfg.get("chatbot", {}).get("name", "Assistant")

    identity_language = getattr(getattr(getattr(app_cfg, "chatbot", None), "identity", None), "language", None) \
                        or raw_cfg.get("chatbot", {}).get("identity", {}).get("language", "en-US")

    # Read store entries for this user
    rag_entries = []
    if rag_last > 0:
        try:
            with open(STORE.path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if entry.get("user_name") == user_name:
                        rag_entries.append(entry)
        except FileNotFoundError:
            pass
        rag_entries = rag_entries[-rag_last:]

    return {
        "active_profile": state.active_profile,
        "user_name": user_name,
        "session": sess,
        "tts_enabled": state.tts_enabled,
        "stt_enabled": state.stt_enabled,
        "history_max_messages": history_max_messages,
        "short_term_turns": buf.turns[-history_max_messages:],
        "pending_count": buf.count,
        "last_injected_notes": getattr(buf, "last_injected_notes", []),
        "rag_entries_for_user": rag_entries[-5:],  # last 5 for this user
        "identity_language": identity_language,
        "identity_name": identity_name,
        "system_template_path": str(TEMPLATE_PATH),
    }


@app.get("/debug/last_ollama_payload")
def debug_last_ollama_payload():
    """
    Return the most recent Ollama request we sent (endpoint + payload + timestamp).
    Helpful for verifying system prompt, messages, options, etc.
    """
    rec = get_last_ollama_payload()
    if rec is None:
        return JSONResponse({"ok": False, "message": "No Ollama payload recorded yet."}, status_code=404)
    return JSONResponse(rec)


# ---------- New: Memory export/import ----------
@app.get("/memory/export")
def memory_export(profile: Optional[str] = None):
    rag_conf = raw_cfg.get("rag", {}) if isinstance(raw_cfg, dict) else {}
    store_path = rag_conf.get("store_path")
    if not store_path:
        raise HTTPException(status_code=500, detail="No store_path configured")
    fs_path = str(ROOT / store_path)
    if not os.path.exists(fs_path):
        raise HTTPException(status_code=404, detail="Store not found")
    filename = f"rag_{(profile or state.active_profile or 'default')}.jsonl"
    return FileResponse(fs_path, media_type="application/octet-stream", filename=filename)


@app.post("/memory/import")
async def memory_import(file: UploadFile = File(...)):
    rag_conf = raw_cfg.get("rag", {}) if isinstance(raw_cfg, dict) else {}
    store_path = rag_conf.get("store_path")
    if not store_path:
        raise HTTPException(status_code=500, detail="No store_path configured")
    fs_path = str(ROOT / store_path)
    os.makedirs(os.path.dirname(fs_path), exist_ok=True)
    data = await file.read()
    with open(fs_path, "ab") as f:
        if os.path.getsize(fs_path) > 0:
            f.write(b"\n")
        f.write(data)
    return {"ok": True, "bytes_appended": len(data)}


@app.get("/memory/list", response_model=MemoryListOut)
def memory_list(
        user: Optional[str] = Query(None),
        session: Optional[str] = Query(None),
        tags: Optional[str] = Query(None, description="Comma-separated tags"),
        types: Optional[str] = Query(None, description="Comma-separated types (e.g. fact,summary)"),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
):
    """
    List items from the JSONL RAG store.
    - Identify items by `idx` (line number) so they can be deleted later.
    - Filters: user, session, tags, types
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    type_list = [t.strip() for t in types.split(",")] if types else None

    entries = _read_store_all()
    # Attach idx = original line number
    indexed = []
    for i, e in enumerate(entries):
        if _matches_filters(e, user, session, tag_list, type_list):
            item = dict(e)
            item["idx"] = i
            # keep a compact projection
            item.setdefault("text", e.get("text") or e.get("note") or "")
            item.setdefault("type", e.get("type") or "")
            item.setdefault("tags", e.get("tags") or [])
            item.setdefault("session", e.get("session") or "")
            item.setdefault("user_name", e.get("user_name") or "")
            item.setdefault("ts", e.get("ts") or "")
            indexed.append(item)

    total = len(indexed)
    items = indexed[offset: offset + limit]
    return MemoryListOut(total=total, items=items)


@app.post("/memory/delete")
def memory_delete(inp: MemoryDeleteIn):
    """
    Delete specific lines (by idx) from the store.
    NOTE: idx refers to the current line-number positions; if you plan multiple deletes,
    call list → delete once with all idx to avoid reindex surprises.
    """
    if not inp.idx:
        raise HTTPException(status_code=400, detail="idx is required")
    to_delete = set(int(i) for i in inp.idx)

    entries = _read_store_all()
    kept = [e for i, e in enumerate(entries) if i not in to_delete]
    removed = len(entries) - len(kept)
    _write_store_all(kept)

    return {"ok": True, "removed": removed, "remaining": len(kept)}


@app.post("/memory/flush")
def memory_flush(inp: MemoryFlushIn):
    """
    Bulk delete entries by user and/or session.
    - If both user and session are None, refuse (too destructive).
    """
    if not inp.user and not inp.session:
        raise HTTPException(status_code=400, detail="Specify user and/or session to flush.")

    entries = _read_store_all()
    kept = []
    removed = 0
    for e in entries:
        if _matches_filters(e, user=inp.user, session=inp.session, tags=None, types=None):
            removed += 1
        else:
            kept.append(e)
    _write_store_all(kept)
    return {"ok": True, "removed": removed, "remaining": len(kept)}


@app.post("/memory/clean")
def memory_clean(inp: MemoryCleanIn):
    """
    De-duplicate entries for a user (optional).
    - Deduplication key = normalized text (lowercased, collapsed spaces).
    - Keeps the MOST RECENT occurrence of each unique text.
    - If keep_latest is set, after dedup we keep only that many latest items for the user.
    If 'user' is None, applies to ALL users.
    """
    entries = _read_store_all()

    # We'll process per user to be safe
    def uname(e):
        return e.get("user_name") or ""

    # Partition by user
    by_user: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        u = uname(e)
        by_user.setdefault(u, []).append(e)

    def process_list(lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Walk from newest to oldest so we keep the first we see.
        # Heuristic "newest" = existing order; jsonl appends at end, so reverse.
        seen = set()
        out_rev = []
        for e in reversed(lst):
            key = _normalize_text(e.get("text") or e.get("note") or "")
            # empty texts we treat as unique entries; keep them
            dedup_key = key if key else None
            if dedup_key is None or dedup_key not in seen:
                if dedup_key:
                    seen.add(dedup_key)
                out_rev.append(e)
        # restore chronological order
        out = list(reversed(out_rev))
        return out

    new_entries: List[Dict[str, Any]] = []
    total_removed = 0

    for user_name, lst in by_user.items():
        if inp.user and user_name != inp.user:
            # untouched
            new_entries.extend(lst)
            continue

        cleaned = process_list(lst)

        # Optional trim to most recent N (after dedup)
        if inp.keep_latest is not None:
            try:
                k = max(0, int(inp.keep_latest))
            except Exception:
                k = 0
            if k < len(cleaned):
                removed_here = len(cleaned) - k
                total_removed += removed_here
                cleaned = cleaned[-k:]  # keep most recent k
        # Count removed by difference
        total_removed += (len(lst) - len(cleaned))
        new_entries.extend(cleaned)

    # Write back
    _write_store_all(new_entries)

    return {"ok": True, "removed": total_removed, "remaining": len(new_entries)}
