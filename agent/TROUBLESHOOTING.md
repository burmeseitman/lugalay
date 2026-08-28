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

## The eyes see nothing / "camera gave no picture"

Check it directly:

```bash
agent/voice/.venv/bin/python agent/eyes/look.py --check    # Windows: agent\voice\.venv\Scripts\python
```

The error names the likely cause. In order of how often it is actually the
problem:

1. **Another program is holding the camera.** Every platform gives the device to
   one process at a time. The hands board (`agent/hands/`) keeps the webcam open
   for as long as its browser tab is on screen, so close that tab before looking.
   Zoom, Teams, FaceTime and Photo Booth do the same.

2. **The OS is blocking it**, and where that switch lives differs:

   | platform | where |
   |---|---|
   | macOS | System Settings > Privacy & Security > Camera — switch on the app that runs Lugalay (`Lugalay.app`, or your terminal when running from a checkout) |
   | Windows | Settings > Privacy & security > Camera — turn on **both** "Camera access" and "Let desktop apps access your camera" |
   | Linux | no permission system: check `/dev/video0` exists and you are in the `video` group (`sudo usermod -aG video $USER`, then log out and back in) |

   On macOS the permission belongs to the *parent* app, not to Python. A
   background process with no window may never get to show the prompt at all,
   which is why running `look.py --check` once from a normal terminal is the
   fastest way to trigger it.

   **Two macOS traps, both of which look exactly like "permission denied"
   even when the switch is clearly on:**

   - *Granted while it was running.* macOS decides a program's camera access
     when the process starts. Turning the switch on under a running Lugalay
     changes nothing until you quit and reopen it.
   - *Freshly rebuilt without a stable signature.* By default the build uses
     an ad-hoc signature, which is a new identity every time. macOS sees a
     different program and the grant does not apply. Run this once to fix it
     for good:

     ```
     packaging/setup-signing.sh
     ```

     It creates a self-signed cert in a dedicated keychain, prompts for your
     login password once to trust it for code signing, and future builds pick
     it up automatically via `packaging/sign.sh`. From then on the Authority
     is stable across builds and TCC keeps the permission.

   `tccutil reset Camera com.lugalay.app` clears whatever macOS has stored and
   lets the prompt appear again from scratch — do this after switching from an
   ad-hoc to a signed build so the old permission entry does not linger.
   lets the prompt appear again from scratch.

3. **opencv is missing from the voice environment.** The error says so outright.
   Fix: `pip install opencv-python-headless`

   It must be the **headless** build. The GUI build needs `libGL.so.1` and GTK,
   which minimal Linux installs do not have, and Lugalay never opens a window —
   it only captures frames.

If the photo comes out black rather than failing, the camera opened before
auto-exposure settled. Raise `WARMUP_FRAMES` in `agent/eyes/camera.py`.

If a machine has several cameras and Lugalay is looking through the wrong one,
set `eyes.device` in `agent/config.json` to 1, 2, ... until `look.py` shows the
right picture.

## Lugalay describes something that isn't there

He was handed a photo he could not actually read and guessed anyway. Look at
`agent/eyes/frames/latest.jpg` yourself — that is exactly what he saw. If it is
dark or blurred, the fix is holding the thing steadier and closer, not changing
the prompt.

If the frame looks fine and the description is still wrong, the trigger phrase
fired on a sentence where nothing was being shown, so he described the room. The
phrase list lives in `agent/eyes/look.py` (`TRIGGERS_MY` / `TRIGGERS_EN`) and can
be overridden per-machine with `eyes.triggers_my` / `eyes.triggers_en` in
`agent/config.json`.

## "cross-site request refused"

Something asked one of the local servers to do something and did not come from
one of its own pages. That is deliberate.

Both servers listen on 127.0.0.1, which sounds private but is not: every page
open in the browser can reach 127.0.0.1 as well. Before this check, a website
could quietly POST to `/open` and put a page of its choosing on the screen, or
to `/look` and take a photo through the webcam. Now every request has to prove
it came from Lugalay itself.

What is allowed through:

- the face and board pages talking to their own server
- anything that is not a browser — `curl`, `present.py`, Lugalay's own tools —
  because those send no `Origin` or `Sec-Fetch-Site` header at all
- a `Host` header naming 127.0.0.1 or localhost, and nothing else, which is
  what stops a hostile domain resolving itself to this machine

If a legitimate tool of your own starts getting 403s, it is sending browser
headers it should not; send the request without `Origin`, or from the page
itself. Do not widen `local_request` in `agent/bus.py` to make it go away —
that check is the only thing between the webcam and the open internet.

## Using OpenAI, Groq or another hosted model instead of Claude

The brain can be any service that speaks the OpenAI chat API — OpenAI itself,
Groq, Together, OpenRouter, DeepSeek, or anything else that follows that shape
(Fireworks, xAI, a self-hosted vLLM, and so on).

Two fields in `agent/config.json` under `brain`:

```
"engine": "openai",
"remote": { "api_key": "sk-..." }
```

`engine` picks the preset — one of `openai`, `groq`, `together`, `openrouter`,
`deepseek` — which sets a URL and a default model. Only `api_key` is required.

For something not in the list, leave engine as `openai` and give a URL and
model of your own:

```
"engine": "openai",
"remote": {
  "url": "https://api.fireworks.ai/inference",
  "model": "accounts/fireworks/models/qwen3-235b-a22b",
  "api_key": "..."
}
```

The key can also come from the `OPENAI_API_KEY` environment variable — useful
for keeping it out of the file when you share a machine.

**Tools.** A hosted model gets the same four tools the local one does:
`read_memory`, `remember`, `open_page`, `show_card`. The provider has to
support tool calling for this to actually fire; every mainstream one does.

**Failure.** If the remote refuses, the log says why and the local model takes
over if one is available. Set `engine` to `auto` for Claude first, hosted
second, local third — but that only fires when Claude itself is broken; a
working Claude is preferred over any hosted alternative.

## Better Burmese voices via Google Cloud TTS

Microsoft Edge only ships two Burmese voices, so the five personas share
them via rate and pitch — which is why they all sound similar. Google Cloud
has four (Wavenet A/B, Standard A/B) and better quality; enabling it makes
each persona sound distinctly its own.

**Setup:**

1. Open <https://console.cloud.google.com>, pick a project (or make one).
2. Search for "Cloud Text-to-Speech API" and enable it.
3. Under APIs & Services → Credentials, create an API key.
4. Paste it into `agent/config.json` (or `~/Lugalay/agent/config.json` for
   the packaged app):

   ```
   "tts": { "api_key": "AIzaSy..." }
   ```

Restart the app. Nothing else to do — the key is auto-detected by its
`AIzaSy` prefix and Google Cloud becomes primary; Edge stays as the fallback
for a bad key, a rate limit or a network blip.

**Free tier:** 4M chars/month for Standard voices, 1M for Wavenet. A daily
conversation is orders of magnitude below either.

**Persona → voice mapping:**

| persona | voice base |
|---|---|
| Aung, Zaw | Wavenet-A (male, younger) |
| U Ba | Standard-A (male, older — sounds distinct) |
| Hnin | Wavenet-B (female, younger) |
| Mya | Wavenet-B (female, tweaked older) |

Override per persona with `voice.my_google` in the face config.

**Troubleshooting:** the log tags TTS attempts. A `gcloud refused (400)` line
usually means the key is wrong or the API is not enabled on that project.
`gcloud refused (429)` is a rate limit. Both fall back to Edge automatically.

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

### He sounds like a textbook, not like a person

The speaking style is a prompt, and it lives in a file you can edit:

```
agent/voice/prompts/spoken_burmese.md
```

It is re-read on **every turn**, so save the file and the very next sentence
he says already follows it. No restart, no rebuild.

Everything above the first `---` is a note to whoever is editing and is cut off
before the model ever sees it. Keep that separator or the note gets read as
instructions.

What actually moves the needle, in order:

1. **The examples.** A wrong/right pair for the exact phrasing that bothers you
   does more than another paragraph of rules. Add the sentence he got wrong and
   the one you wanted underneath it.
2. **Naming the particle.** "Never သည်" works. "Be less formal" does not.
3. **Sentence length.** Long sentences are where written register creeps back
   in, because the grammar needs joining words that only exist in စာပေဟန်.

A packaged build cannot edit the file inside the app. Put your version at
`~/Lugalay/agent/voice/prompts/spoken_burmese.md` and it wins. Or point
`language.my_prompt_file` in `agent/config.json` anywhere you like.

Note that this costs tokens on every single turn — the shipped prompt is about
450 of them. If replies start feeling slower to begin, that is where it went;
trim the examples first, they are the expensive part.

Markdown, emojis and parentheses are stripped from the reply in code, not by
the prompt, in `clean_spoken_text` in `agent/voice/voice.py`. If something is
still being read out that should not be, fix it there — a prompt is a request,
that function is a guarantee.

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
