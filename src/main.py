from __future__ import annotations
from pathlib import Path
import argparse

from bot.config import load_config, get_system_template_path
from bot.chatbot import Chatbot
from bot.cli import chat_once, chat_loop
from bot.logger import TranscriptLogger, LogConfig

def parse_args():
    p = argparse.ArgumentParser(description="LocalAI Bot runner")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--ask", help="Ask a single question and print the answer")
    group.add_argument("--chat", action="store_true", help="Start interactive chat loop")
    p.add_argument("--session", help="Optional session name for logging", default=None)
    return p.parse_args()

def main():
    args = parse_args()
    cfg_path = Path(__file__).parents[1] / "config" / "default.yaml"
    app_cfg, raw = load_config(cfg_path)
    template_path = get_system_template_path(cfg_path, raw)

    bot = Chatbot(app_cfg)
    print(bot.whoami())
    print()

    # Logging (file transcript)
    log_cfg_raw = raw.get("logging", {}) if isinstance(raw, dict) else {}
    logs_dir = log_cfg_raw.get("dir", "logs")
    prefix = log_cfg_raw.get("session_prefix", "chat")
    log_cfg = LogConfig(directory=(Path(__file__).parents[1] / logs_dir), session_prefix=prefix)
    logger = TranscriptLogger(log_cfg, session_name=args.session)

    # RAG config
    rag_cfg = raw.get("rag", {}) if isinstance(raw, dict) else {}

    if args.ask:
        chat_once(app_cfg, str(template_path), args.ask, logger=logger, rag_cfg=rag_cfg)
    else:
        chat_loop(app_cfg, str(template_path), logger=logger, rag_cfg=rag_cfg, session_name=args.session)

if __name__ == "__main__":
    main()
