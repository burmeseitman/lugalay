#!/usr/bin/env python3
"""Record real Burmese speech and show exactly how the router sees it.

Everything tuned so far used synthetic TTS audio. This uses your voice, your
microphone and your room, and keeps the recording so it can be replayed while
tuning instead of asking you to speak again and again.
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, sounddevice as sd, soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(os.path.dirname(HERE), "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "langtest.log")
out = open(LOG, "w", encoding="utf-8", errors="replace")
def say(m=""):
    print(m, flush=True); out.write(m + "\n"); out.flush()

RATE, SECS = 16000, 5
print()
print("  Say ONE sentence in BURMESE.")
print("  For example:  မင်္ဂလာပါ။ ဒီနေ့ ဘာလုပ်ကြမလဲ။")
print()
print("  I will wait until I actually HEAR you, then record 5 seconds.")
print("  Watch the bar — if it never moves, the microphone is the problem.")
print()

frames = []
armed = {"go": False, "waited": 0.0}

def cb(indata, n, t, status):
    frames.append(indata.copy())

stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32",
                        callback=cb, blocksize=1024)
stream.start()

# ── wait for real speech instead of recording into the void ──
t0 = time.time()
seen_any = 0.0
while True:
    time.sleep(0.15)
    if not frames:
        continue
    recent = np.concatenate(frames[-8:], axis=0).flatten()
    lvl = float(np.sqrt(np.mean(np.square(recent))))
    seen_any = max(seen_any, lvl)
    bar = "#" * min(40, int(lvl * 600))
    waited = time.time() - t0
    print(f"\r   waiting  |{bar:<40}| {lvl:.4f}   {waited:4.0f}s", end="", flush=True)
    if lvl > 0.020:                       # clearly speech, not room tone
        break
    if waited > 40:
        print()
        break

print()
if seen_any < 1e-6:
    stream.stop(); stream.close()
    say("="*64)
    say("MICROPHONE DELIVERED PURE SILENCE — every sample exactly zero.")
    say("")
    say("  This is not a quiet room (a quiet room reads about 0.005).")
    say("  macOS is not giving this app the microphone, or another app")
    say("  is holding it exclusively (a call, FaceTime, Teams, a meeting).")
    say("")
    say("  1. Quit anything that might hold the mic (Teams, FaceTime, Zoom)")
    say("  2. System Settings > Privacy & Security > Microphone > enable Terminal")
    say("  3. Cmd-Q Terminal fully, then run this again")
    say("="*64)
    out.close()
    sys.exit(1)

print("   RECORDING — keep talking...")
frames.clear()
time.sleep(SECS)
stream.stop(); stream.close()

audio = np.concatenate(frames, axis=0).flatten().astype("float32")
wav = os.path.join(LOGDIR, "burmese_sample.wav")
sf.write(wav, audio, RATE)
say("="*64)
say("Lugalay language-router diagnostic (REAL voice)")
say("="*64)
say(f"saved      : {wav}")
say(f"duration   : {len(audio)/RATE:.1f}s   peak {np.abs(audio).max():.3f}  "
    f"rms {np.sqrt(np.mean(np.square(audio))):.4f}")
say("")

from faster_whisper import WhisperModel
THREADS = os.cpu_count() or 4
MODELS = os.path.join(HERE, "models")

for lid_size in ("base", "small", "medium"):
    try:
        m = WhisperModel(lid_size, device="cpu", compute_type="int8",
                         cpu_threads=THREADS,
                         download_root=os.path.join(MODELS, "whisper"))
        t0 = time.time()
        lang, prob, all_probs = m.detect_language(audio)
        top = sorted(all_probs.items(), key=lambda kv: -kv[1])[:5] \
              if isinstance(all_probs, dict) else []
        say(f"LID {lid_size:7} -> {lang} p={prob:.2f}  ({time.time()-t0:.2f}s)")
        if top:
            say(f"            top5: " + ", ".join(f"{k}={v:.2f}" for k, v in top))
    except Exception as e:
        say(f"LID {lid_size:7} -> failed: {e}")
say("")

say("What each transcriber makes of it:")
for label, name, lang in [("BURMESE model", "whisper-my-turbo", "my"),
                          ("ENGLISH model", "small.en", "en")]:
    try:
        path = os.path.join(MODELS, name)
        m = WhisperModel(path if os.path.isdir(path) else name, device="cpu",
                         compute_type="int8", cpu_threads=THREADS,
                         download_root=os.path.join(MODELS, "whisper"))
        t0 = time.time()
        segs, _ = m.transcribe(audio, language=lang, beam_size=1,
                               vad_filter=True, condition_on_previous_text=False)
        text = " ".join(s.text for s in segs).strip()
        say(f"  {label} ({time.time()-t0:4.1f}s): {text[:100]}")
    except Exception as e:
        say(f"  {label}: failed {e}")
say("="*64)
say(f"(saved to {LOG})")
out.close()
