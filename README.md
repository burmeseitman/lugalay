<p align="center">
  <img src="assets/logo.svg" alt="Lugalay" width="700"/>
</p>

# Lugalay

A personal AI desktop companion for macOS: a **mind**, a **mouth**, a **face**, a pair of **hands**, and a set of **eyes**. It listens in Burmese and English, answers with natural colloquial spoken rhythm, and watches you from an animated pixel avatar. 

```
you speak ──▶ Faster-Whisper / Google STT (my-MM / en-US)
                         │
                         ▼
        Brain: OpenAI Codex Plus / Claude / Ollama
                         │
                         ▼
        Diglossia Normalizer & Phonetic Transliteration
                         │
                         ├─▶ English ─▶ Kokoro-82M ONNX (Local)
                         └─▶ Burmese ─▶ Gemini 2.5 Flash TTS (Primary)
                                      └─▶ Microsoft Edge-TTS (Free Fallback)
                                                    │
                                                    ▼
                                          agent/bus/state.json
                                                    │
                                                    ▼
                                       Animated Face & Settings UI
```

---

## 🚀 Quick Start

Double-click **`Lugalay.app`** in `/Applications`, or run:

```bash
open ~/Applications/Lugalay.app
```

Then just talk. There is no key to hold: it calibrates the room, listens to your voice, and speaks back naturally.

---

## ⌨️ Keys & Shortcuts

| Key | Action |
|---|---|
| **1-5** | Switch persona — face **and** voice (Aung, Hnin, Zaw, Mya, U Ba) |
| **S** | Open **In-App Settings** modal (configure names, languages, persona, API keys) |
| **B** | Overlay mode: pins transparent avatar directly onto your desktop |
| **F** | Fullscreen toggle |
| **H** | Toggle Hands & Vision board |
| **⌘Q** | Quit (cleanly terminates audio loop, servers, and window) |

---

## ⚙️ In-App Settings

Click the **`⚙ Settings`** button (or press **`S`**) at any time to customize:

* **Assistant & User Names**: Personalize how you address each other.
* **Listening Language**: Choose between `Burmese Only`, `English Only`, or `Auto / Bilingual`.
* **Speaking Language**: Choose `Burmese`, `English`, or `Match Spoken`.
* **Voice & Face Persona**: Select between 5 distinct avatar styles and vocal profiles.
* **Gemini API Key**: Add your key for expressive Gemini 2.5 Flash TTS. Without a key, Lugalay runs 100% free with Microsoft Edge-TTS.

---

## 🎭 The Five Personas

| Key | Persona | Gender | Burmese Voice | English Voice |
|---|---|---|---|---|
| **1** | **Aung** | Male (24) | `my-MM-ThihaNeural` (Clear, Energetic) | `am_adam` |
| **2** | **Hnin** | Female (22) | `my-MM-NilarNeural` (Sweet, Calm) | `af_heart` |
| **3** | **Zaw** | Male (42) | `my-MM-ThihaNeural` (Mature, Confident) | `bm_lewis` |
| **4** | **Mya** | Female (40) | `my-MM-NilarNeural` (Warm, Polite) | `bf_emma` |
| **5** | **U Ba** | Male (68) | `my-MM-ThihaNeural` (Wise, Resonant) | `bm_george` |

---

## 🧠 Brain Engines & Vision

* **OpenAI Codex Plus (`engine: "codex"`)**: Runs headless via `codex exec --json` on your existing **ChatGPT / Codex Plus subscription** with zero API token overhead.
* **Claude / Local Ollama Fallback**: Cascades gracefully to local offline models (`qwen3.6`, `llama3`) or Claude when offline.
* **Eyes & Camera Vision**: Ask visual questions (*"Look at this"*, *"ဒီဟာကို ကြည့်ပေးပါ"*) to analyze camera frames in real time.
* **Diglossia Normalizer**: Automatically converts literary Burmese (`သည်`, `မည်`, `၌`) into colloquial spoken prose (`တယ်`, `မယ်`, `မှာ`), enforces gender particles (`ခင်ဗျာ` vs `ရှင့်`), and applies 300+ phonetic transliterations for technical terms.

---

## 📦 Building & Diagnostics

Run diagnostics from the repository root:

```bash
./agent/voice/diagnose.sh           # Test dependencies, models, mic, and brain
./agent/voice/diagnose.sh mic       # Test microphone capture
./agent/voice/diagnose.sh lang      # Test language identification
```

To build a standalone macOS application:

```bash
/Users/minhtet/Projects/lugalay/agent/voice/.venv/bin/pyinstaller --noconfirm --clean packaging/lugalay.spec
bash packaging/sign.sh dist/Lugalay.app
```
