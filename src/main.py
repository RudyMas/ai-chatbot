from __future__ import annotations
from pathlib import Path
import argparse

from bot.config import AppConfig, UserConfig
from bot.chatbot import Chatbot
from bot.cli import chat_once, chat_loop
from bot.logger import TranscriptLogger, LogConfig
from bot.profiles import load_profile

def parse_args():
    p = argparse.ArgumentParser(description="LocalAI Bot runner")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--ask", help="Ask a single question and print the answer")
    group.add_argument("--chat", action="store_true", help="Start interactive chat loop")
    p.add_argument("--session", help="Optional session name for logging", default=None)
    p.add_argument("--user", help="Override username (default from profile)", default=None)
    p.add_argument("--profile", help="Profile name or path (e.g., 'default', 'alice', 'config/profiles/pat.yaml')", default="default")
    return p.parse_args()

def main():
    args = parse_args()

    # Load selected profile
    app_cfg, raw = load_profile(args.profile)
    template_path = str(Path(load_profile(args.profile)[2]))

    # Allow runtime override of username
    if args.user:
        app_cfg.user = UserConfig(name=args.user)

    bot = Chatbot(app_cfg)
    print(bot.whoami())
    print(f"Talking to: {app_cfg.user.name}")
    print(f"Profile: {args.profile}\n")

    # Logging (file transcript)
    log_cfg_raw = raw.get("logging", {}) if isinstance(raw, dict) else {}
    logs_dir = log_cfg_raw.get("dir", "logs")
    prefix = log_cfg_raw.get("session_prefix", "chat")
    log_cfg = LogConfig(directory=(Path(__file__).parents[1] / logs_dir), session_prefix=prefix)
    logger = TranscriptLogger(log_cfg, session_name=args.session, user_name=app_cfg.user.name)

    # RAG config
    rag_cfg = raw.get("rag", {}) if isinstance(raw, dict) else {}

    if args.ask:
        chat_once(app_cfg, template_path, args.ask, logger=logger, rag_cfg=rag_cfg)
    else:
        chat_loop(app_cfg, template_path, logger=logger, rag_cfg=rag_cfg, session_name=args.session)

if __name__ == "__main__":
    main()
