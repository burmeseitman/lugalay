<p align="center">
  <img src="assets/logo.svg" alt="Lugalay" width="700"/>
</p>

# Lugalay

A personal AI assistant that lives on this machine: a **mind**, a **mouth**, a
**face**, and a pair of **hands**. It listens in Burmese and English, answers in natural spoken Burmese or English, and watches you from a pixel avatar. The brain is Claude Code; almost everything else runs locally.

```
you speak ──▶ Language Filter / Google STT ──┬─▶ Google STT (my-MM / en-US) ─┐
                                             └─▶ Whisper Local Fallback      ─┤
                                                                              ├─▶ Claude / LLM ──┬─▶ Kokoro (English)
                                                                              │                  └─▶ Microsoft Neural (Burmese)
                                                                              │                            │
                                                      agent/bus/state.json ◀──┴────────────────────────────┘
                                                               │
                                                               └──▶ the face & settings UI
```

## Run it

Double-click **`Lugalay.app`** in `/Applications`, on your Desktop, or in this folder. It opens a native window with no terminal and no browser. Everything that would have scrolled past goes to `agent/logs/app.log`.

Then just talk. There is no key to hold: it calibrates the room, waits for you to speak, and answers when you stop.

For a typed session instead, double-click `Lugalay Chat.command` on the Desktop, or run:

```bash
cd ~/Projects/luagalay && claude
```

## Keys & Shortcuts

| Key | Does |
|---|---|
| **1-5** | Switch persona — face **and** voice (Aung, Hnin, Zaw, Mya, U Ba) |
| **S** | Open **In-App Settings** modal (configure names, languages, face, API keys) |
| **B** | Overlay mode: strips the card, bar, and caption; avatar pinned on top of desktop |
| **F** | Fullscreen toggle |
| **⌘Q** | Quit (cleanly terminates audio loop, servers, and window) |

The window has no title bar. Drag anywhere to move it.

## ⚙️ In-App Settings

Click the **`⚙ Settings`** button (or press **`S`**) at any time to customize your assistant:

* **Your Name & Assistant Name**: Customize what the assistant calls you and what you call the assistant.
* **Listening Language (နားထောင်မည့် ဘာသာစကား)**:
  * `Burmese (မြန်မာ သီးသန့်)`: Locks STT strictly to Burmese (`my-MM`), preventing language confusion.
  * `English Only`: Locks STT strictly to English (`en-US`).
  * `Auto / Bilingual`: Automatically identifies whether you spoke Burmese or English.
* **Speaking Language (ပြန်လည်ဖြေကြားမည့် ဘာသာစကား)**:
  * `Burmese (မြန်မာ)`: Assistant always responds in 100% natural conversational Burmese.
  * `English`: Assistant always responds in English.
  * `Match Spoken`: Responds in whichever language you spoke.
* **Voice & Face**: Seamlessly select between the 5 personas.
* **Voice API Key**: Enter an optional ElevenLabs or Cloud API key (masked with password show/hide toggle).

## The Five Personas

Each is a different pixel human — gender, age, hair, style, skin — **and each speaks in its own distinct voice.**

| Key | Persona | Burmese Voice | English Voice |
|---|---|---|---|
| **1** | **Aung** (Male, 24) | `my-MM-ThihaNeural` (Clear, Energetic) | `am_adam` |
| **2** | **Hnin** (Female, 22) | `my-MM-NilarNeural` (Sweet, Calm) | `af_heart` |
| **3** | **Zaw** (Male, 42) | `my-MM-ThihaNeural` (Mature, Confident) | `bm_lewis` |
| **4** | **Mya** (Female, 40) | `my-MM-NilarNeural` (Warm, Polite) | `bf_emma` |
| **5** | **U Ba** (Male, 68) | `my-MM-ThihaNeural` (Deep, Wise Elder) | `bm_george` |

Whoever is on screen, the avatar expressions lip-sync to the conversation:

| State | Expression |
|---|---|
| **idle** | Soft smile, blinking, natural glance movements |
| **listening** | Brows raised, eyes wide, sound bars scaled to your microphone input |
| **thinking** | Brows furrowed, eyes looking up with thought bubble animation |
| **speaking** | Mouth lip-syncs dynamically with live audio output amplitude |

## Language Capabilities

### 👂 Hearing Burmese (Speech-to-Text)
* **Google Speech-to-Text (`my-MM`)**: Uses in-memory high-fidelity FLAC streaming for **95%+ recognition accuracy** on native Burmese speech, catching colloquial Burmese words, loanwords, and numbers accurately.
* **Offline Whisper Fallback**: Automatically takes over if internet connection is offline.

### 🗣️ Speaking Burmese (Text-to-Speech)
* **Native Microsoft Neural Engine**: High-fidelity Burmese neural models (`ThihaNeural` & `NilarNeural`) fine-tuned with tailored pitch, speech rate, and conversational pacing per persona.
* **Clean Stream Synthesis**: All Burmese replies are synthesized as single coherent streams to prevent unnatural phrase repetition or voice hopping.

## The Brain & Local Fallback

`brain.engine` is `auto`: **Claude Code normally, `qwen3:8b` locally if Claude fails** (usage limits, offline, billing).

| Capability | Claude | Local LLM (qwen3:8b) |
|---|---|---|
| Burmese quality | Natural, intelligent | Coherent |
| Reads & writes memory vault | **Yes** | No |
| Runs tools & self-repairs | **Yes** | No |
| Offline capability | No | **Yes** |
| Cost | Subscription / API | Free |

## Project Structure

| Path | Description |
|---|---|
| `Lugalay.app` | Standalone macOS application bundle |
| `CLAUDE.md` | Persona prompt and conversational instructions |
| `memory/` | Long-term memory vault (Obsidian markdown format) |
| `agent/config.json` | Single source of truth for all configurations |
| `agent/app.py` | App entry point and native window manager |
| `agent/setup.py` | First-run setup initialization |
| `agent/voice/` | Listening, thinking, and speaking audio pipeline |
| `agent/face/` | WebGL pixel avatar and settings server (`:7317`) |
| `agent/hands/` | Webcam gesture detection server (`:7318`) |
| `agent/bus/` | Lightweight IPC state bus (`state.json`, `face.json`) |
| `agent/logs/` | Runtime application logs (`app.log`, `voice.log`) |

## Permissions on macOS

- **Microphone**: Required for listening to your voice.
- **Camera**: Optional (only used if hand-tracking gesture board is activated).

## Diagnostics & Troubleshooting

Run diagnostic checks from the repository root:

```bash
./agent/voice/diagnose.sh           # Test all dependencies, models, mic, and brain
./agent/voice/diagnose.sh mic       # Test microphone capture and audio levels
./agent/voice/diagnose.sh lang      # Test language identification and STT accuracy
```
