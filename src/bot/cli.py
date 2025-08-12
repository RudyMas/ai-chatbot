from __future__ import annotations
from bot.llm.ollama import generate
from bot.config import AppConfig
from bot.rag.summarizer import summarize_chunk
from bot.rag.store import RAGStore

def chat_once(app_cfg: AppConfig, system_template_path: str, prompt: str, logger=None, rag_cfg=None):
    if logger: logger.log("user", prompt)
    answer = generate(prompt, app_cfg, system_template_path)
    if logger: logger.log("assistant", answer)
    # one-off: no chunking
    print(f"\nAssistant: {answer}\n")

def chat_loop(app_cfg: AppConfig, system_template_path: str, logger=None, rag_cfg=None, session_name: str | None = None):
    print("Interactive chat started. Type /exit to quit.\n")

    # RAG setup
    enabled = bool(rag_cfg and rag_cfg.get("enabled", True))
    chunk_messages = int(rag_cfg.get("chunk_messages", 6)) if enabled else 0
    max_words = int(rag_cfg.get("summary_max_words", 120)) if enabled else 0
    tags = list(rag_cfg.get("tags", ["session-summary"])) if enabled else []
    store_path = rag_cfg.get("store_path", "data/rag/store.jsonl") if enabled else None
    store = RAGStore(store_path) if enabled else None

    # rolling buffer of last N messages (pairs of role,text)
    buf: list[tuple[str, str]] = []
    msg_count = 0
    sess = session_name or "session"

    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user:
            continue
        if user.lower() in ("/exit", "/quit"):
            print("Bye!")
            break

        if logger: logger.log("user", user)
        buf.append(("user", user))
        msg_count += 1

        answer = generate(user, app_cfg, system_template_path)
        if logger: logger.log("assistant", answer)
        buf.append(("assistant", answer))
        msg_count += 1

        print(f"Assistant: {answer}\n")

        # Every chunk_messages total messages, create a tiny summary note
        if enabled and chunk_messages > 0 and (msg_count % chunk_messages == 0):
            note = summarize_chunk(app_cfg, system_template_path, buf[-chunk_messages:], max_words)
            entry = RAGStore.make_summary_entry(sess, note, tags)
            store.append(entry)
