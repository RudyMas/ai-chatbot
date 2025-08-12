from __future__ import annotations
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
    print(f"Interactive chat started as {app_cfg.user.name}. Type /exit to quit.\n")

    # RAG summary config
    enabled = bool(rag_cfg and rag_cfg.get("enabled", True))
    chunk_messages = int(rag_cfg.get("chunk_messages", 6)) if enabled else 0
    max_words = int(rag_cfg.get("summary_max_words", 120)) if enabled else 0
    tags = list(rag_cfg.get("tags", ["session-summary"])) if enabled else []
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
            entry = RAGStore.make_summary_entry(sess, app_cfg.user.name, note, tags)
            store.append(entry)
