from __future__ import annotations
from bot.llm.ollama import generate
from bot.config import AppConfig

def chat_once(app_cfg: AppConfig, system_template_path: str, prompt: str, logger=None):
    if logger: logger.log("user", prompt)
    answer = generate(prompt, app_cfg, system_template_path)
    if logger: logger.log("assistant", answer)
    print(f"\nAssistant: {answer}\n")

def chat_loop(app_cfg: AppConfig, system_template_path: str, logger=None):
    print("Interactive chat started. Type /exit to quit.\n")
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
        answer = generate(user, app_cfg, system_template_path)
        if logger: logger.log("assistant", answer)
        print(f"Assistant: {answer}\n")
