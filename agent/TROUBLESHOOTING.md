# Lugalay: when something breaks

Lugalay, this file is for you. The person you work for should not be reading
it — when they say
something is broken, work this list yourself.

First, always:

```bash
./agent/voice/run.sh --check
```

That prints a green or red line for every dependency, the model files, the
microphone, and the brain.

---

## The brain says "Credit balance is too low"

The voice loop shells out to `claude -p`, and that spawned process bills
differently from an interactive Claude Code session. If `--check` shows this,
nothing on this machine is broken — the account cannot serve the request.

- Check the balance and plan at https://console.anthropic.com/settings/billing
- Confirm the CLI is logged into the right account: `claude` then `/status`
- Everything else (mic, whisper, Kokoro, face, hands) works regardless; test
  the rest of the pipeline with `./agent/voice/run.sh --mock-brain --text "hello"`

## Nothing happens when I hold the talk key

**Run the diagnostic first — it answers this with facts, not guesses:**

```bash
./agent/voice/.venv/bin/python agent/voice/keytest.py
```

Run it from the SAME terminal app Lugalay is launched from; macOS grants
permission per app bundle, so a result from anywhere else means nothing. It
reports whether the process is trusted, whether a keyboard event tap can be
created, and every key it actually sees during a 20-second window. Results also
land in `agent/logs/keytest.log`.

macOS needs **two separate permissions**, and the second is the one people miss:

1. System Settings ▸ Privacy & Security ▸ **Accessibility**
2. System Settings ▸ Privacy & Security ▸ **Input Monitoring** ← keyboard taps
   need this one, and being in Accessibility does not cover it

Add the terminal app (`/System/Applications/Utilities/Terminal.app` for the
Desktop shortcuts) to both, then **quit it fully with Cmd-Q** — closing the
window is not enough, because permissions are applied when the process starts.

The voice loop checks both at startup via `AXIsProcessTrusted()` and a test
event tap, and says exactly which one is missing. It does **not** infer trouble
from silence: an earlier version warned after 12 seconds with no key events,
which cried wolf at anyone who listened to the greeting before speaking.

If the diagnostic shows monitoring works but `cmd_r` never appears, that key is
not being reported separately by your keyboard. Pick any key the diagnostic did
see and set `mic.key` in `agent/config.json` — for example `<alt_r>` or `<f13>`.
To change the key, edit `mic.key` in `agent/config.json` — pynput syntax,
e.g. `<cmd_r>`, `<alt_r>`, `<f13>`, `<home>`.

## It hears nothing / transcribes garbage

- System Settings ▸ Privacy & Security ▸ **Microphone** — enable the terminal app
- Check the input device is the one you think: `--check` lists them
- Speaking Burmese? `stt.model` is `small.en`, which is **English-only**.
  Set `stt.model` to `small` and `stt.language` to `null` in `agent/config.json`.
  Multilingual is slower and slightly weaker on English — that is the trade.

## No sound comes out

- `./agent/voice/run.sh --say "testing"` isolates speech from everything else
- If Kokoro fails to load, the voice automatically falls back to macOS `say`,
  and the terminal says so. Check `agent/voice/models/` still holds
  `kokoro-v1.0.onnx` (310 MB) and `voices-v1.0.bin` (26 MB).
- To change voice: `tts.voice` in `agent/config.json`. `bm_lewis` and `bm_george`
  are British male, `am_michael` American male, `af_heart` American female.

## The face is stuck on idle / says "bus offline"

The face reads `agent/bus/state.json` through the face server. If it shows
"bus offline", the server on port 7317 is not running. Start it:
`python3 agent/face/server.py`. If the state file is stale, any voice session
resets it on exit.

## The hands board won't start

- Camera: System Settings ▸ Privacy & Security ▸ **Camera** — enable the browser
- The board falls back to **mouse mode** automatically when there is no camera,
  so it is never fully dead
- Everything is vendored in `agent/hands/vendor/` — it needs no internet. If the
  model or wasm went missing, re-fetch per the notes in `memory/projects/lugalay-agent.md`

## Ports already in use

`face_port` (7317) and `hands_port` (7318) in `agent/config.json`. Change and restart.
Find the squatter with `lsof -i :7317`.

## Rebuilding the voice environment

```bash
cd agent/voice && rm -rf .venv && uv venv --python 3.12 .venv \
  && uv pip install --python .venv/bin/python -r requirements.txt
```

Python is pinned to 3.12 on purpose: the audio wheels lag behind the system 3.14.

## "I need your approval" — but nobody can approve in a voice session

A spoken session has no way to show a permission prompt, so anything not
pre-allowed simply fails. The allowlist lives in `.claude/settings.json` at the
agent's home:

- **allowed**: reading anything in the home, writing to `memory/**`, editing
  `agent/config.json`, running `present.py` and the self-check
- **denied outright**: `rm`, `sudo`, `git push`, `git commit`, and reading
  secrets (`.env`, `~/.ssh`, `~/Keys`, the credentials file)
- **everything else**: refused, and Lugalay says so out loud

If Lugalay needs a new ability for real work, add one precise rule to the
`allow` list — never widen it to `Bash(*)`, and never switch
`brain.permission_mode` to `"auto"` just to stop the refusals. That flag maps to
`bypassPermissions`, which ignores this file completely.

## Burmese

Lugalay answers in Burmese by default (set in `CLAUDE.md`, not in config) and
speaks it with Microsoft's `my-MM-ThihaNeural` voice through `edge-tts`.

**This one path needs the internet.** Kokoro has no Burmese, and neither does
macOS — there is no offline Burmese voice on this machine. If the network is
down, Burmese sentences are skipped rather than read aloud in an English voice,
which would be unintelligible. English sentences still work offline through Kokoro.

Voice switching is automatic and by **script**, not by a setting: any sentence
containing Myanmar characters goes to `edge-tts`, everything else to Kokoro.
A mixed answer switches voices mid-reply, which is what natural bilingual speech
sounds like. To change the Burmese voice, set `tts.burmese_voice` in
`agent/config.json` — `my-MM-ThihaNeural` (male) or `my-MM-NilarNeural` (female).

### Spoken Burmese input does not work

You can **speak English** or **type Burmese**. You cannot speak Burmese.

This is a Whisper limitation, measured on this machine, not a bug to fix:

| model | Burmese result | time for 3.3s audio |
|---|---|---|
| `small` | Sinhala-script garbage | 22.5s |
| `large-v3-turbo` | garbage | 21.3s |

Whisper has almost no Burmese training data at any size, and the large models are
also far too slow on CPU for conversation. Do not "fix" this by switching
`stt.model` — it has been tried and it is worse in both accuracy and latency.

Real options, if spoken Burmese ever matters enough:
- **Azure Speech** — has proper `my-MM` recognition. Paid, needs a key, online.
- **MMS-ASR** (`facebook/mms-1b-all`) — offline, covers Burmese, but pulls in
  torch (~2.5 GB) and quality is moderate.
