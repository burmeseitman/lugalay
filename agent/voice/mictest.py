#!/usr/bin/env python3
"""Can Lugalay actually hear the microphone?

macOS returns SILENCE rather than an error when microphone permission is
denied, so 'it cannot hear me' and 'it was never allowed to listen' look
identical from inside the program. This tells them apart.

Run it from the SAME terminal app you launch Lugalay from.
"""
import os, sys, time
import numpy as np, sounddevice as sd

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(os.path.dirname(HERE), "logs", "mictest.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)
out = open(LOG, "w", encoding="utf-8", errors="replace")

def say(m=""):
    print(m, flush=True); out.write(m + "\n"); out.flush()

say("="*62); say("Lugalay microphone diagnostic"); say("="*62)

try:
    default_in = sd.query_devices(kind="input")
    say(f"Default input : {default_in['name']}")
    say(f"Sample rate   : {int(default_in['default_samplerate'])} Hz")
except Exception as e:
    say(f"Default input : ERROR {e}")
say("")
say("All input devices:")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        say(f"   [{i}] {d['name']}  ({d['max_input_channels']}ch)")
say("")

RATE, SECS = 16000, 8
print()
print("  When you press return, speak normally for 8 seconds.")
print("  Say something like: 'Hello Lugalay, can you hear me?'")
try:
    input("  Press return when you are ready... ")
except EOFError:
    pass
say(f"Recording {SECS} seconds — TALK NOW...")
say("")
frames = []
def cb(indata, n, t, status):
    frames.append(indata.copy())

try:
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32",
                        callback=cb, blocksize=1024):
        for s in range(SECS, 0, -1):
            time.sleep(1)
            lvl = 0.0
            if frames:
                recent = np.concatenate(frames[-16:], axis=0).flatten()
                lvl = float(np.sqrt(np.mean(np.square(recent))))
            bar = "#" * min(40, int(lvl * 600))
            say(f"   {s}s  |{bar:<40}| rms={lvl:.5f}")
except Exception as e:
    say(f"\nERROR opening the microphone: {e}")
    say("That is usually macOS refusing access. See the verdict below.")

audio = np.concatenate(frames, axis=0).flatten() if frames else np.zeros(0, "float32")
peak = float(np.abs(audio).max()) if audio.size else 0.0
rms  = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
say("")
say("-"*62)
say(f"samples captured : {audio.size}")
say(f"peak amplitude   : {peak:.6f}")
say(f"rms              : {rms:.6f}")
say("")

if audio.size == 0:
    say("VERDICT: the stream never delivered any audio at all.")
    ok = False
elif peak < 1e-6:
    say("VERDICT: PURE DIGITAL SILENCE — every sample is exactly zero.")
    say("         The microphone is not being delivered to this app.")
    say("         This is macOS denying Microphone permission.")
    ok = False
elif peak < 0.01:
    say("VERDICT: audio arrived but it is extremely quiet.")
    say("         Check the input volume, or that the right device is default.")
    ok = False
else:
    say("VERDICT: MICROPHONE WORKS — real audio captured.")
    ok = True
say("")
if not ok:
    say("  Fix: System Settings > Privacy & Security > Microphone")
    say("       enable the terminal app you launched this from,")
    say("       then QUIT it fully with Cmd-Q and run this again.")
else:
    say("  Now checking whether Whisper can understand it...")
    try:
        import warnings; warnings.filterwarnings("ignore")
        from faster_whisper import WhisperModel
        m = WhisperModel("small.en", device="cpu", compute_type="int8",
                         download_root=os.path.join(HERE, "models", "whisper"))
        segs, _ = m.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        text = " ".join(s.text for s in segs).strip()
        say(f"  Whisper heard: {text!r}" if text else
            "  Whisper heard nothing — audio present but no clear speech.")
    except Exception as e:
        say(f"  Whisper failed: {e}")
say("-"*62)
say(f"(saved to {LOG})")
out.close()
