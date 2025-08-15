# LocalAI Chatbot – Jarvis Edition

An interactive local AI chatbot with **RAG memory**, **text-to-speech (TTS)**, **speech-to-text (STT)**, and a browser-based UI.  
Built for friendly conversations with a persistent personality, voice interaction, and long-term memory export/import.

---

## ✨ Features

- 🗣 **Two-way voice** — Speak to Jarvis (STT) and hear him reply (TTS).
- 🧠 **RAG-based memory** — Remembers facts across sessions, with import/export.
- 🎭 **Custom personalities** — Profiles define tone, style, and boundaries.
- 🔍 **Debug tools** — Inspect live memory & profile context.
- 🎤 **Live recording** — Press-to-record transcription via browser.
- 🔄 **Profile switching** — Change personality instantly.
- 💾 **Long-term storage** — JSONL memory file per user/session.

---

## 📦 Requirements

- **Windows 10/11** (64-bit)
- [Anaconda / Miniconda](https://docs.conda.io/en/latest/miniconda.html) (recommended)
- NVIDIA GPU with CUDA 12.x for GPU-accelerated STT (optional but recommended)
- Python 3.11.x

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/RudyMas/ai-chatbot.git
cd ai-chatbot
```

### 2. Create a Conda environment

```bash
conda create -n ai-chatbot python=3.11
conda activate ai-chatbot
```

### 3. Install dependencies

#### Base environment
```bash
pip install -e .
```

#### For GPU-accelerated STT (optional, NVIDIA only)
```bash
nvidia-smi  # Check your CUDA version
conda install -c nvidia cuda-runtime=12.x cudnn=9.1
pip install ctranslate2
```

---

## ⚙️ Configuration

Profiles are stored in:
```
config/profiles/<profile-name>.yaml
```

You can find the default profile for Jarvis in `config/default.yaml`.`

---

## 📜 System Prompt

The system prompt is defined in:
```
src/bot/prompt/system_prompt.txt
```

This is the initial context Jarvis uses to understand his role and capabilities. You can customize it to change how Jarvis interacts with users.
You can also add additional context in `config/profiles/<profile-name>.yaml` under the `context` key.

---

## ▶️ Running the server

```bash
  uvicorn server.api:app --reload
```

---

## 🌐 Using the Web UI

1. Open your browser to:
   ```
   http://127.0.0.1:8000/static/index.html
   ```
2. Enter your username and optionally a session ID.
3. Choose your profile and enable **TTS** / **STT** as needed.
4. Use the buttons to:
   - 🎤 Start/Stop recording
   - 🔊 Replay last reply
   - 🪲 Debug / view context
   - ⬇️ Export memory
   - ⬆️ Import memory

---

## 📁 Memory Management

- **Export** — Downloads a `.jsonl` file of Jarvis’s memory.
- **Import** — Uploads a `.jsonl` file to restore memory.
- **Debug** — Inspect active profile, conversation turns, and facts.

---

## 🔮 Future Features

- `/google` command for real-time internet search
- Webpage reading mode (`/browse`)
- Voice personality presets
- Mobile-friendly layout

---

## 📝 License

Apache License 2.0 — See `LICENSE` for details.

---

## ❤️ Credits

Developed by **Rudy Mas**  
Special thanks to the open-source AI community.
