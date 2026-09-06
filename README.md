<p align="center">
  <img src="assets/logo.svg" alt="Lugalay" width="700"/>
</p>

# Lugalay

A personal AI desktop companion for macOS: a **mind**, a **mouth**, a **face**, a pair of **hands**, and a set of **eyes**. It listens in Burmese and English, answers with natural colloquial spoken rhythm, and watches you from an animated pixel avatar. 

```mermaid
flowchart TD
    User([🎙️ You Speak]) --> STT[Faster-Whisper / Google STT]
    
    STT --> Brain[🧠 Brain: OpenAI Codex Plus / Claude / Ollama]
    Brain --> Normalizer[📝 Diglossia Normalizer & Transliteration]
    
    Normalizer -->|English| Kokoro[🇺🇸 Kokoro-82M ONNX Local TTS]
    Normalizer -->|Burmese| BurmeseTTS{TTS Provider}
    
    BurmeseTTS -->|Primary| Gemini[✨ Gemini 2.5 Flash Expressive TTS]
    BurmeseTTS -->|Free Fallback| Edge[⚡ Microsoft Edge-TTS]
    
    Kokoro --> Bus[(agent/bus/state.json)]
    Gemini --> Bus
    Edge --> Bus
    
    Bus --> UI[🎭 Animated Face & Settings UI]
```

---

## 🛠️ Tech Stack

| Domain | Technologies & Frameworks |
|---|---|
| **Core & Desktop Engine** | ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat-square&logo=python&logoColor=white) ![PyWebView](https://img.shields.io/badge/PyWebView-1B1F23?style=flat-square) ![macOS](https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white) ![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat-square&logo=numpy&logoColor=white) |
| **Brain & Reasoning LLMs** | ![OpenAI Codex](https://img.shields.io/badge/OpenAI_Codex_Plus_/_GPT--4o-412991?style=flat-square&logo=openai&logoColor=white) ![Claude](https://img.shields.io/badge/Anthropic_Claude-D97706?style=flat-square&logo=anthropic&logoColor=white) ![Gemini](https://img.shields.io/badge/Google_Gemini-8E75C2?style=flat-square&logo=google&logoColor=white) ![Ollama](https://img.shields.io/badge/Ollama_(Qwen/LLaMA)-000000?style=flat-square&logo=ollama&logoColor=white) |
| **Speech-to-Text (STT)** | ![Faster-Whisper](https://img.shields.io/badge/Faster--Whisper_(Local_int8)-000000?style=flat-square&logo=openai&logoColor=white) ![Google Speech](https://img.shields.io/badge/Google_Speech_STT-4285F4?style=flat-square&logo=google&logoColor=white) |
| **Text-to-Speech (TTS)** | ![Gemini TTS](https://img.shields.io/badge/Gemini_2.5_Flash_TTS-8E75C2?style=flat-square&logo=google&logoColor=white) ![Microsoft Edge-TTS](https://img.shields.io/badge/Microsoft_Edge--TTS-0078D7?style=flat-square&logo=microsoft&logoColor=white) ![Kokoro ONNX](https://img.shields.io/badge/Kokoro--82M_ONNX-005CED?style=flat-square&logo=onnx&logoColor=white) |
| **Vision & Gestures** | ![MediaPipe](https://img.shields.io/badge/Google_MediaPipe_WASM-0078D4?style=flat-square&logo=google&logoColor=white) ![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white) |
| **Build & Distribution** | ![PyInstaller](https://img.shields.io/badge/PyInstaller-FFE873?style=flat-square&logo=python&logoColor=black) ![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white) |

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
