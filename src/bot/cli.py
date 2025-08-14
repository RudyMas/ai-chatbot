from __future__ import annotations
from typing import List, Tuple
from bot.llm.ollama import generate, generate_chat
from bot.config import AppConfig
from bot.rag.summarizer import summarize_chunk
from bot.rag.store import RAGStore
from bot.rag.retriever import SimpleRetriever

def _context_block(notes: list[str]) -> str:
    if not notes:
        return ""
    lines = "\n".join(f"- {n}" for n in notes)
    return f"Relevant notes:\n{lines}\n\n"

def _build_retriever(rag_cfg, user_name: str | None):
    require_user_match = bool(rag_cfg.get("require_user_match", False))
    retr = SimpleRetriever(
        rag_cfg.get("store_path", "data/rag/store.jsonl"),
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

def chat_once(app_cfg: AppConfig, system_template_path: str, prompt: str, logger=None, rag_cfg=None):
    notes = []
    if rag_cfg and rag_cfg.get("enabled", True):
        retr, top_k, max_note_words, min_score, fallback_recent = _build_retriever(rag_cfg, app_cfg.user.name)
        notes = retr.top_k_notes(prompt, top_k, max_note_words, min_score=min_score, fallback_recent=fallback_recent)
    final_prompt = _context_block(notes) + prompt

    if logger: logger.log("user", prompt, user_name=app_cfg.user.name)
    answer = generate(final_prompt, app_cfg, system_template_path)
    if logger: logger.log("assistant", answer)
    print(f"\nAssistant: {answer}\n")

def chat_loop(app_cfg: AppConfig, system_template_path: str, logger=None, rag_cfg=None, session_name: str | None = None):
    print(f"Interactive chat started as {app_cfg.user.name}. Type /exit to quit.\n")

    enabled = bool(rag_cfg and rag_cfg.get("enabled", True))
    chunk_messages = int(rag_cfg.get("chunk_messages", 6)) if enabled else 0
    max_words = int(rag_cfg.get("summary_max_words", 120)) if enabled else 0
    tags = list(rag_cfg.get("tags", ["session-summary"])) if enabled else []
    store_path = rag_cfg.get("store_path", "data/rag/store.jsonl") if enabled else None
    store = RAGStore(store_path) if enabled else None

    retr, top_k, max_note_words, min_score, fallback_recent = _build_retriever(rag_cfg or {}, app_cfg.user.name)

    buf: List[Tuple[str, str]] = []
    msg_count = 0
    sess = session_name or "session"
    use_chat_api = True
    hist_max = int((rag_cfg or {}).get("history_max_messages", 8))

    while True:
        try:
            user = input(f"{app_cfg.user.name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user:
            continue
        if user.lower() in ("/exit", "/quit"):
            print("Bye!")
            break

        notes = retr.top_k_notes(user, top_k, max_note_words, min_score=min_score, fallback_recent=fallback_recent)
        final_user = _context_block(notes) + f"{app_cfg.user.name}: {user}"

        if logger: logger.log("user", user, user_name=app_cfg.user.name)
        buf.append(("user", f"{app_cfg.user.name}: {user}"))
        msg_count += 1

        history_slice = buf[-hist_max:] if hist_max > 0 else buf
        if use_chat_api:
            answer = generate_chat(history_slice[:-1], history_slice[-1][1], app_cfg, system_template_path)
        else:
            answer = generate(final_user, app_cfg, system_template_path)

        if logger: logger.log("assistant", answer)
        buf.append(("assistant", answer))
        msg_count += 1

        print(f"Assistant: {answer}\n")

        if enabled and chunk_messages > 0 and (msg_count % chunk_messages == 0):
            recent = buf[-chunk_messages:]
            note = summarize_chunk(app_cfg, system_template_path, recent, max_words)
            entry = RAGStore.make_summary_entry(sess, app_cfg.user.name, note, tags)
            store.append(entry)
