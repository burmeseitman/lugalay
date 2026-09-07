<p align="center">
  <img src="assets/logo.svg" alt="Lugalay" width="700"/>
</p>

# Lugalay

A personal AI desktop companion for macOS, Windows, and Linux: a **mind**, a **mouth**, a **face**, a pair of **hands**, and a set of **eyes**. It listens in Burmese and English, answers with natural colloquial spoken rhythm, and watches you from an animated pixel avatar. 

```mermaid
flowchart TB
    subgraph Perception ["👁️ Perception & Input Layer"]
        Mic["🎙️ Microphone Voice"] --> STT["🎧 Faster-Whisper / Google STT"]
        Cam["📷 Camera Feed"] --> Eyes["👁️ Eyes (OpenCV Frame Capture)"]
        Gest["🖐️ Video Stream"] --> Hands["✋ MediaPipe WASM (Hand Gestures)"]
    end

    subgraph CoreBrain ["🧠 Cognitive Brain & Memory System"]
        STT --> Brain["🧠 LLM Brain Engine<br/>(OpenAI Codex Plus / Claude / Gemini / Ollama)"]
        Eyes -.->|Visual QA Frame| Brain
        
        Brain <-->|read_memory / remember| MemVault[("💾 Obsidian Memory Vault<br/>• profile.md (User Context)<br/>• projects/*.md (Tasks)<br/>• daily/YYYY-MM-DD.md<br/>• lessons & people")]
    end

    subgraph ActionTools ["⚡ Tool Execution Engine"]
        Brain -->|Tool Calling| Tools{"🛠️ Tool Dispatcher"}
        Tools -->|open_page| Browser["🌐 Browser / YouTube / Web"]
        Tools -->|show_card| Board["📋 Hands Presentation Board"]
    end

    subgraph Linguistic ["📝 Linguistic & Expression Normalizer"]
        Brain --> Normalizer["📝 Diglossia Normalizer<br/>(Literary ➔ Colloquial Spoken Burmese & 300+ Tech Phonetics)"]
        Normalizer --> Emotion["🎭 Persona & Emotion Engine<br/>(5 Persona Profiles)"]
    end

    subgraph SpeechSynthesis ["🗣️ Speech Synthesis (Mouth)"]
        Emotion -->|Burmese Primary| GeminiTTS["✨ Gemini 2.5 Flash Expressive TTS"]
        Emotion -->|Burmese Fallback| EdgeTTS["⚡ Microsoft Edge-TTS (Thiha / Nilar)"]
        Emotion -->|English Spoken| KokoroTTS["🇺🇸 Kokoro-82M ONNX Local TTS"]
    end

    subgraph SyncUI ["🎭 Realtime Event Bus & Display"]
        GeminiTTS & EdgeTTS & KokoroTTS --> Bus[("📡 agent/bus/state.json<br/>(Audio & State IPC Bus)")]
        Hands --> Bus
        Bus --> FaceUI["🎭 PyWebView Desktop Interface<br/>• Animated Pixel Avatar (Lipsync & Eyes)<br/>• In-App Settings Modal (S key)<br/>• Overlay Transparent Desktop Mode (B key)"]
        Board --> FaceUI
    end
```

---

## 🛠️ Tech Stack

| Domain | Technologies & Frameworks |
|---|---|
| **Core & Desktop Engine** | ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat-square&logo=python&logoColor=white) ![PyWebView](https://img.shields.io/badge/PyWebView-1B1F23?style=flat-square) ![macOS](https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white) ![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows&logoColor=white) ![Linux](https://img.shields.io/badge/Linux-FCC624?style=flat-square&logo=linux&logoColor=black) ![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat-square&logo=numpy&logoColor=white) |
| **Brain & Reasoning LLMs** | ![OpenAI Codex](https://img.shields.io/badge/OpenAI_Codex_Plus_/_GPT--4o-412991?style=flat-square&logo=openai&logoColor=white) ![Claude](https://img.shields.io/badge/Anthropic_Claude-D97706?style=flat-square&logo=anthropic&logoColor=white) ![Gemini](https://img.shields.io/badge/Google_Gemini-8E75C2?style=flat-square&logo=google&logoColor=white) ![Ollama](https://img.shields.io/badge/Ollama_(Qwen/LLaMA)-000000?style=flat-square&logo=ollama&logoColor=white) |
| **Long-Term Memory** | ![Obsidian](https://img.shields.io/badge/Obsidian_Markdown_Vault-483699?style=flat-square&logo=obsidian&logoColor=white) ![IPC Bus](https://img.shields.io/badge/JSON_State_Bus-333333?style=flat-square) |
| **Speech-to-Text (STT)** | ![Faster-Whisper](https://img.shields.io/badge/Faster--Whisper_(Local_int8)-000000?style=flat-square&logo=openai&logoColor=white) ![Google Speech](https://img.shields.io/badge/Google_Speech_STT-4285F4?style=flat-square&logo=google&logoColor=white) |
| **Text-to-Speech (TTS)** | ![Gemini TTS](https://img.shields.io/badge/Gemini_2.5_Flash_TTS-8E75C2?style=flat-square&logo=google&logoColor=white) ![Microsoft Edge-TTS](https://img.shields.io/badge/Microsoft_Edge--TTS-0078D7?style=flat-square&logo=microsoft&logoColor=white) ![Kokoro ONNX](https://img.shields.io/badge/Kokoro--82M_ONNX-005CED?style=flat-square&logo=onnx&logoColor=white) |
| **Vision & Gestures** | ![MediaPipe](https://img.shields.io/badge/Google_MediaPipe_WASM-0078D4?style=flat-square&logo=google&logoColor=white) ![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white) |
| **Build & Distribution** | ![PyInstaller](https://img.shields.io/badge/PyInstaller-FFE873?style=flat-square&logo=python&logoColor=black) ![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white) |

---

## 🚀 Quick Start

Download the pre-built application for your operating system from [GitHub Releases](https://github.com/burmeseitman/lugalay/releases):

* **macOS (Apple Silicon & Intel)**: Open the `.dmg` file and drag `Lugalay.app` to `/Applications`.
* **Windows (x64)**: Unzip `Lugalay-windows-x86_64.zip` and run `Lugalay.exe`.
* **Linux (x64)**: Extract `Lugalay-linux-x86_64.tar.gz` and run `./Lugalay`.

Or run directly from source:

```bash
python3 agent/app.py
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
| **⌘Q / Ctrl+Q** | Quit (cleanly terminates audio loop, servers, and window) |

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

## 🧠 Brain Engines, Memory & Tools

* **OpenAI Codex Plus (`engine: "codex"`)**: Runs headless via `codex exec --json` on your existing **ChatGPT / Codex Plus subscription** with zero API token overhead.
* **Claude / Local Ollama Fallback**: Cascades gracefully to local offline models (`qwen3.6`, `llama3`) or Claude when offline.
* **💾 Long-Term Memory (Obsidian Vault)**: Stores persistent context across sessions in pure Markdown:
  * `memory/profile.md`: User identity, background, preferences, and workflows.
  * `memory/projects/*.md`: Active projects, architecture decisions, and task states.
  * `memory/daily/YYYY-MM-DD.md`: Chronological daily summaries and conversations.
  * `memory/lessons/*.md`: Rules, corrections, and guidelines.
* **🛠️ Built-in Tool Calling**:
  * `read_memory(topic)`: Autonomous memory recall to look up past context before answering.
  * `remember(note, file)`: Writes durable facts and updates directly to the vault.
  * `open_page(url)`: Opens web pages, YouTube videos, or research links directly in the browser upon request.
  * `show_card(text, title)`: Generates and pins interactive notes/cards onto the visual presentation board.
* **👁️ Eyes & Camera Vision**: Multimodal visual QA (*"Look at this"*, *"ဒီဟာကို ကြည့်ပေးပါ"*) capturing live OpenCV camera frames for instant reasoning.
* **🖐️ Hands & Presentation Board**: Google MediaPipe WASM hand landmarker for real-time gesture control and canvas interaction.
* **📝 Diglossia Normalizer**: Automatically converts literary Burmese (`သည်`, `မည်`, `၌`) into colloquial spoken prose (`တယ်`, `မယ်`, `မှာ`), enforces gender particles (`ခင်ဗျာ` vs `ရှင့်`), and applies 300+ phonetic transliterations for technical terms.

---

## 📦 Building & Diagnostics

Run diagnostics from the repository root:

```bash
./agent/voice/diagnose.sh           # Test dependencies, models, mic, and brain
./agent/voice/diagnose.sh mic       # Test microphone capture
./agent/voice/diagnose.sh lang      # Test language identification
```

To build standalone application binaries locally:

```bash
pyinstaller --noconfirm --clean packaging/lugalay.spec

# On macOS (to apply code signature):
bash packaging/sign.sh dist/Lugalay.app
```
