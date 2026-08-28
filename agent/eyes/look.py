#!/usr/bin/env python3
"""Lugalay looking at what you are holding up.

    python3 look.py                 # grab a frame, print where it went
    python3 look.py --check         # is the camera usable at all?

The voice loop imports `wants_to_look` and `capture`: when you ask Lugalay to
look at something, it takes one photo and hands Claude the path, which Claude
reads with its own Read tool. There is no vision API and no second model —
the brain already has eyes, it just needed something to point them at.
"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import camera  # noqa: E402

# Deliberately tight. A bare "what's this?" is something he says all day without
# holding anything up; every phrase here names looking, seeing, or the camera.
TRIGGERS_MY = [
    "ဒါကိုကြည့်", "ဒါကြည့်", "ဒီကိုကြည့်", "ဒီမှာကြည့်", "ဒီပုံကိုကြည့်",
    "ဒီပုံကြည့်", "ပုံကိုကြည့်", "ကင်မရာကိုကြည့်", "ကင်မရာကြည့်",
    "ဒါကိုမြင်လား", "မြင်လား", "ဒါကိုရှင်းပြ", "ဒီပုံကိုရှင်းပြ",
    "ငါပြထားတာ", "ဒါကိုဖတ်ပြ",
]
TRIGGERS_EN = [
    "look at this", "look at that", "look at my", "look at the camera",
    "can you see this", "do you see this", "see this", "can you see what",
    "check this out", "what am i holding", "what am i showing",
    "explain this diagram", "explain this drawing", "read this for me",
    "what does this say", "what's on the screen i'm holding",
]

# What Claude is told once a photo exists. Kept as one paragraph on purpose:
# the reply is going to be spoken, and the brain already has spoken-style rules.
NOTE = (
    "\n\n[The user just held something up to the webcam and a photo of it was "
    "taken: {path} — read that image file with your Read tool and answer about "
    "what is actually in it. If the photo is too dark or blurry to make out, "
    "say so plainly and ask him to hold it steadier or closer, rather than "
    "guessing. Remember this is spoken aloud: describe it in two or three "
    "sentences of plain prose.]"
)

FAILED = (
    "\n\n[The user asked you to look at something, but the camera could not be "
    "used: {error}. Tell him in one sentence that you cannot see right now and "
    "why. Do not pretend to describe anything.]"
)


def config():
    try:
        import bus
        return bus.config().get("eyes", {}) or {}
    except Exception:
        return {}


def wants_to_look(text):
    """True if he is asking Lugalay to look at something in front of the camera."""
    if not text:
        return False
    cfg = config()
    if not cfg.get("enabled", True):
        return False
    low = text.lower()
    my = cfg.get("triggers_my") or TRIGGERS_MY
    en = cfg.get("triggers_en") or TRIGGERS_EN
    return any(t in text for t in my) or any(t in low for t in en)


def capture(index=None):
    """Take the photo. Returns (path, None) or (None, error message)."""
    cfg = config()
    idx = cfg.get("device", 0) if index is None else index
    try:
        return camera.snapshot(index=idx), None
    except camera.CameraError as e:
        return None, str(e)
    except Exception as e:                     # a broken opencv build, a bad index
        return None, f"{type(e).__name__}: {e}"


def augment(text, index=None):
    """The spoken sentence, with the photo (or the reason there isn't one) appended."""
    path, err = capture(index)
    return text + (NOTE.format(path=path) if path else FAILED.format(error=err))


def main():
    if "--check" in sys.argv:
        path, err = capture()
        if err:
            print(f"eyes: NOT working — {err}", file=sys.stderr)
            return 1
        print(f"eyes: working — {path}")
        return 0
    t0 = time.time()
    path, err = capture()
    if err:
        print(f"could not look: {err}", file=sys.stderr)
        return 1
    print(f"{path}  ({os.path.getsize(path)//1024} KB, {time.time()-t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
