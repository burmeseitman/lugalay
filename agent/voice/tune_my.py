#!/usr/bin/env python3
"""Read one known Burmese sentence; compare decoder settings objectively.

Until now the Burmese model has been tuned by eyeballing output with no
ground truth. This gives a target sentence, records you reading it, and
scores every decode configuration by character error rate.
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, sounddevice as sd, soundfile as sf

TARGET = "မင်္ဂလာပါ။ ဒီနေ့ ဘာအလုပ်တွေ လုပ်ကြမလဲ။"

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(os.path.dirname(HERE), "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "tune_my.log")
out = open(LOG, "w", encoding="utf-8", errors="replace")
def say(m=""):
    print(m, flush=True); out.write(m + "\n"); out.flush()

def cer(ref, hyp):
    """Character error rate — Burmese has no word boundaries, so characters
    are the only honest unit."""
    ref = "".join(ref.split()); hyp = "".join(hyp.split())
    if not ref: return 1.0
    d = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(hyp, 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j-1] + 1, prev + (rc != hc))
            prev = cur
    return d[len(hyp)] / len(ref)

RATE = 16000
print()
print("  Read this sentence out loud, clearly:")
print()
print(f"      {TARGET}")
print()
print("  I will wait until I hear you, then record 6 seconds.")
try: input("  Press return when ready... ")
except EOFError: pass

frames = []
stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32",
                        callback=lambda i,n,t,s: frames.append(i.copy()),
                        blocksize=1024)
stream.start()
t0 = time.time(); seen = 0.0
while True:
    time.sleep(0.15)
    if not frames: continue
    lvl = float(np.sqrt(np.mean(np.square(np.concatenate(frames[-8:],axis=0)))))
    seen = max(seen, lvl)
    print(f"\r   waiting |{'#'*min(40,int(lvl*600)):<40}| {lvl:.4f}", end="", flush=True)
    if lvl > 0.020: break
    if time.time()-t0 > 40: break
print()
if seen < 1e-6:
    say("MICROPHONE SILENT — nothing to tune. Check Privacy & Security > Microphone.")
    sys.exit(1)
print("   RECORDING — read it now...")
frames.clear(); time.sleep(6); stream.stop(); stream.close()

audio = np.concatenate(frames, axis=0).flatten().astype("float32")
wav = os.path.join(LOGDIR, "burmese_target.wav")
sf.write(wav, audio, RATE)

say("="*70)
say("Burmese decoder tuning — scored against a known sentence")
say("="*70)
say(f"target : {TARGET}")
say(f"audio  : {len(audio)/RATE:.1f}s  peak {np.abs(audio).max():.3f}  saved {wav}")
say("")

from faster_whisper import WhisperModel
m = WhisperModel(os.path.join(HERE, "models", "whisper-my-turbo"), device="cpu",
                 compute_type="int8", cpu_threads=os.cpu_count() or 4)

TRIALS = [
    ("beam1 + vad   (current)", dict(beam_size=1, vad_filter=True)),
    ("beam5 + vad",             dict(beam_size=5, vad_filter=True)),
    ("beam5, no vad",           dict(beam_size=5, vad_filter=False)),
    ("beam5, no vad, prompt",   dict(beam_size=5, vad_filter=False,
                                     initial_prompt=TARGET[:12])),
    ("beam8, no vad, patience", dict(beam_size=8, vad_filter=False, patience=1.5)),
]
best = None
for label, kw in TRIALS:
    t0 = time.time()
    try:
        segs, _ = m.transcribe(audio, language="my",
                               condition_on_previous_text=False, **kw)
        text = " ".join(s.text for s in segs).strip()
    except Exception as e:
        say(f"  {label:26} FAILED {e}"); continue
    e = cer(TARGET, text)
    dt = time.time()-t0
    say(f"  {label:26} CER {e*100:5.1f}%  {dt:4.1f}s")
    say(f"  {'':26} {text[:70]}")
    if best is None or e < best[0]: best = (e, label, dt)
say("")
if best:
    say(f"BEST: {best[1]}  (CER {best[0]*100:.1f}%, {best[2]:.1f}s)")
say("="*70)
out.close()
