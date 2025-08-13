from __future__ import annotations
from typing import List
from bot.llm.ollama import generate
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
    return retr, top_k, max_note_words

def _extract_tags_from_text(text: str) -> List[str]:
    # simple hashtag extractor: words like #global #music
    tags: List[str] = []
    cur = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "#":
            j = i + 1
            token = []
            while j < len(text) and (text[j].isalnum() or text[j] in ("-", "_")):
                token.append(text[j])
                j += 1
            if token:
                tags.append("".join(token))
            i = j
        else:
            i += 1
    return list(dict.fromkeys(t.lower() for t in tags))  # dedupe, lowercase

def _strip_hashtags(text: str) -> str:
    # remove standalone hashtags from the fact text
    out = []
    for part in text.split():
        if part.startswith("#") and len(part) > 1:
            continue
        out.append(part)
    return " ".join(out).strip()

def chat_once(app_cfg: AppConfig, system_template_path: str, prompt: str, logger=None, rag_cfg=None):
    # retrieval
    notes = []
    if rag_cfg and rag_cfg.get("enabled", True):
        retr, top_k, max_note_words = _build_retriever(rag_cfg, app_cfg.user.name)
        notes = retr.top_k_notes(prompt, top_k, max_note_words)
    final_prompt = _context_block(notes) + prompt

    if logger: logger.log("user", prompt, user_name=app_cfg.user.name)
    answer = generate(final_prompt, app_cfg, system_template_path)
    if logger: logger.log("assistant", answer)
    print(f"\nAssistant: {answer}\n")

def chat_loop(app_cfg: AppConfig, system_template_path: str, logger=None, rag_cfg=None, session_name: str | None = None):
    print(f"Interactive chat started as {app_cfg.user.name}. Type /exit to quit.")
    print("Commands: /remember <fact> [#tags]   (e.g., /remember I love synthwave #music #global)\n")

    # RAG summary config
    enabled = bool(rag_cfg and rag_cfg.get("enabled", True))
    chunk_messages = int(rag_cfg.get("chunk_messages", 6)) if enabled else 0
    max_words = int(rag_cfg.get("summary_max_words", 120)) if enabled else 0
    tags_default = list(rag_cfg.get("tags", ["session-summary"])) if enabled else []
    store_path = rag_cfg.get("store_path", "data/rag/store.jsonl") if enabled else None
    store = RAGStore(store_path) if enabled else None

    # Retriever (user-scoped)
    retr, top_k, max_note_words = _build_retriever(rag_cfg or {}, app_cfg.user.name)

    buf: list[tuple[str, str]] = []
    msg_count = 0
    sess = session_name or "session"

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

        # Handle /remember command
        if user.lower().startswith("/remember"):
            if not enabled or store is None:
                print("RAG store disabled; cannot remember right now.\n")
                continue
            fact_text = user[len("/remember"):].strip()
            if not fact_text:
                print("Usage: /remember <fact> [#tags]\n")
                continue

            tags = _extract_tags_from_text(fact_text)
            fact_clean = _strip_hashtags(fact_text)

            # Add 'global' tag if user typed #global; otherwise the note is user-scoped
            final_tags = ["manual"] + tags  # 'manual' marks user-added facts

            entry = RAGStore.make_fact_entry(sess, app_cfg.user.name, fact_clean, final_tags)
            store.append(entry)
            if logger: logger.log("user", user, user_name=app_cfg.user.name)
            print("✓ Remembered.\n")
            # refresh retriever cache next turn (lazy: rebuild instance)
            retr, top_k, max_note_words = _build_retriever(rag_cfg or {}, app_cfg.user.name)
            continue

        # retrieval injection
        notes = retr.top_k_notes(user, top_k, max_note_words)
        final_prompt = _context_block(notes) + f"{app_cfg.user.name}: {user}"

        if logger: logger.log("user", user, user_name=app_cfg.user.name)
        buf.append(("user", f"{app_cfg.user.name}: {user}"))
        msg_count += 1

        answer = generate(final_prompt, app_cfg, system_template_path)
        if logger: logger.log("assistant", answer)
        buf.append(("assistant", answer))
        msg_count += 1

        print(f"Assistant: {answer}\n")

        # periodic summaries → scoped to this user
        if enabled and chunk_messages > 0 and (msg_count % chunk_messages == 0):
            note = summarize_chunk(app_cfg, system_template_path, buf[-chunk_messages:], max_words)
            entry = RAGStore.make_summary_entry(sess, app_cfg.user.name, note, tags_default)
            store.append(entry)
