from pathlib import Path
from bot.config import load_config, get_system_template_path
from bot.chatbot import Chatbot
from bot.llm.ollama import generate

def main():
    cfg_path = Path(__file__).parents[1] / "config" / "default.yaml"
    app_cfg, raw = load_config(cfg_path)
    template_path = get_system_template_path(cfg_path, raw)

    bot = Chatbot(app_cfg)
    print(bot.whoami())
    print()

    answer = generate("Introduce yourself in one friendly sentence.", app_cfg, str(template_path))
    print("Model:", app_cfg.llm.model)
    print("Answer:", answer)

if __name__ == "__main__":
    main()
