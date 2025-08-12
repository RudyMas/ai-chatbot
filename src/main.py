from pathlib import Path
from bot.config import load_config, get_system_template_path
from bot.chatbot import Chatbot
from bot.llm.ollama import generate, bind_cfg_helpers

def main():
    cfg_path = Path(__file__).parents[1] / "config" / "default.yaml"
    app_cfg, raw = load_config(cfg_path)
    template_path = get_system_template_path(cfg_path, raw)
    bind_cfg_helpers(app_cfg, str(template_path))

    bot = Chatbot(app_cfg)
    print(bot.whoami())
    print()

    # tiny demo prompt
    answer = generate("Introduce yourself in one friendly sentence.", app_cfg)
    print("Model:", app_cfg.llm.model)
    print("Answer:", answer)

if __name__ == "__main__":
    main()
