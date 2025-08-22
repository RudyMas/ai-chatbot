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
- 🌐 **Web UIs**:
  - `index.html` — Control center (profiles, TTS/STT, memory tools).
  - `viewer.html` — Voice-first interface with continuous listening.
  - `chat.html` — Chat-only interface, similar to ChatGPT.

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
  conda install -c nvidia cuda-runtime=12.x cudnn=9
  pip install ctranslate2
```

If you don't have an NVIDIA GPU, you can skip the CUDA installation and just use CPU-based STT.

Don't forget to change the `stt` section in your profile to use CPU STT:
```yaml
  stt:
    enabled: false
    engine: "faster-whisper"
    model_size: "base"             # tiny/base/small/medium/large-v3
    device: "cuda"                 # "cpu" or "cuda" for GPU
```

---

## Installing Ollama & Models

This project uses [Ollama](https://ollama.ai) to run local large language models (LLMs).

**Install Ollama**  
- Download and install Ollama for your platform from [ollama.ai/download](https://ollama.ai/download).  
- On Windows, you may need to restart your terminal after installation.

**Verify Installation**  

Run the following in a terminal to confirm Ollama is installed and running:  
```bash
  ollama --version
  ollama list
```

**Download a Model**  

This project is configured to use `CognitiveComputations/dolphin-mistral-nemo` by default (see `default.yaml`).  
You can pull it with:  
```bash
  ollama pull CognitiveComputations/dolphin-mistral-nemo
```  
Or pick another model from the [Ollama model library](https://ollama.ai/library).

**Update your config**  

In `config/profiles/default.yaml`, set:
```yaml
  llm:
    model: "your/model:name"
```
Restart the server after making changes.

---

## ⚙️ Profiles

This project uses YAML-based profiles to define the AI’s persona.  
By default, the assistant is configured as **Jarvis**, an intelligent and witty AI helper.

### Example profile (`config/default.yaml`)

```yaml
  chatbot:
    name: "Jarvis"
    identity:
      gender: "male"
      age: 43
      language: "en-US"
      timezone: "Europe/Brussels"
    personality:
      style: "polished, witty, articulate, slightly formal"
      boundaries: "SFW, respectful, never rude or dismissive"

  user:
    name: "User"
```

### Creating your own persona

You can easily create your own AI personality:

Copy `config/default.yaml` to a new file, e.g. `config/profiles/alice.yaml`.  
Edit the `chatbot` section to define:

- **name** → the assistant’s name  
- **identity** → gender, age, language, timezone  
- **personality** → style and boundaries  

---

## 📜 System Prompt

The system prompt is defined in:
```
  src/bot/prompt/system_prompt.txt
```

This is the initial context Jarvis uses to understand his role and capabilities.  
You can customize it to change how Jarvis interacts with users.

You can create different system prompts for different profiles by creating a new file in the same directory, e.g. `system_prompt_alice.txt`, and then referencing it in your profile:

```yaml
  llm:
    system_prompt: "src/bot/prompt/system_prompt_alice.txt"
```

---

## ▶️ Running the server

```bash
  uvicorn server.api:app --reload
```

---

## 🌐 Using the Web UI

Open in your browser:

### **Main control panel:**  
  [http://127.0.0.1:8000/static/index.html](http://127.0.0.1:8000/static/index.html)

Recommended on starting this page first to set up your profile and TTS/STT settings and from there you can access the other UIs.
This way you are sure the right profile is selected and the TTS/STT settings are configured.

- Controls in `index.html`
  - 🗔 Open **Voice Viewer**
  - 💬 Open **Chat**
  - 💡 Demo: Let Jarvis Speak
  - 🔊 Speak last reply
  - 🎤 Start/Stop recording
  - 🪲 Debug
  - 🪲 Open Debug JSON
  - ⬇️ Export memory
  - ⬆️ Import memory

### **Voice Viewer (hands-free):**  
  [http://127.0.0.1:8000/static/viewer.html](http://127.0.0.1:8000/static/viewer.html)

To make sure the UI works correctly, you may need to allow microphone access in your browser settings.

⚠️ **Mute Listening Mode**  
In the **Voice Viewer (viewer.html)**, you’ll find a checkbox labeled **Mute AI (store only)**.  

When enabled:
- The AI will **continue listening** in the background.
- Spoken input is **not responded to immediately**, but instead **stored in the memory buffer**.
- Once mute is disabled, the AI can use everything it “heard” during mute mode as context when responding.
- If you press **Demo Speak**, the AI will immediately respond to what was said during mute mode, and then continue  
  listening silently with mute still active.

This allows the AI to **listen in silently** on conversations, gathering context without interrupting — useful when  
you want it to be aware but not actively speaking.

### **Chat UI (text only):**  
  [http://127.0.0.1:8000/static/chat.html](http://127.0.0.1:8000/static/chat.html)

This is a simple chat interface similar to ChatGPT, where you can type messages and receive text responses from Jarvis.

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
