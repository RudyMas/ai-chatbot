from pathlib import Path
from bot.config import load_config
from bot.chatbot import Chatbot

def main():
    cfg = load_config(Path(__file__).parents[1] / "config" / "default.yaml")
    bot = Chatbot(cfg)
    print(bot.whoami())
    print()
    print(bot.summary())

if __name__ == "__main__":
    main()
