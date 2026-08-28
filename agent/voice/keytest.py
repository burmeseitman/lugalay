#!/usr/bin/env python3
"""Why isn't the talk key working? Answers it with facts, not guesses.

Run it from the SAME terminal app you launch Lugalay from — macOS grants
permission per app bundle, so results from anywhere else mean nothing.
"""
import ctypes, ctypes.util, os, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(os.path.dirname(HERE), "logs", "keytest.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)
out = open(LOG, "w", encoding="utf-8", errors="replace")


def say(m=""):
    print(m, flush=True)
    out.write(m + "\n"); out.flush()


say("=" * 62)
say("Lugalay key diagnostic")
say("=" * 62)

# ── 1. what macOS thinks of this process ──────────────────────────────
try:
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
    lib.AXIsProcessTrusted.restype = ctypes.c_bool
    trusted = lib.AXIsProcessTrusted()
except Exception as e:
    trusted = f"could not check ({e})"
say(f"Accessibility trusted : {trusted}")

# ── 2. can we actually build an event tap? that needs Input Monitoring ──
tap_ok = None
try:
    import Quartz
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
        lambda *a: None, None)
    tap_ok = tap is not None
    if tap:
        Quartz.CFRelease(tap)
except Exception as e:
    tap_ok = f"error: {e}"
say(f"Keyboard event tap    : {tap_ok}")
say(f"Parent process        : {os.popen('ps -o comm= -p %d' % os.getppid()).read().strip()}")
say("")

if trusted is not True or tap_ok is not True:
    say("VERDICT: macOS is blocking keyboard monitoring for this app.")
    say("")
    say("  Accessibility trusted = False  -> add the app under")
    say("      Privacy & Security > Accessibility")
    say("  Event tap = False              -> add the app under")
    say("      Privacy & Security > INPUT MONITORING   <- often the missing one")
    say("")
    say("  After adding it you must QUIT the terminal app fully (Cmd-Q),")
    say("  not just close the window. Permissions apply at process start.")
    say("")

# ── 3. do events actually arrive? ─────────────────────────────────────
say("Now press some keys — including the RIGHT COMMAND key.")
say("Listening for 20 seconds...")
say("")

from pynput import keyboard

seen = collections.Counter()
order = []


def name(k):
    return getattr(k, "name", None) or getattr(k, "char", None) or str(k)


def on_press(k):
    n = name(k)
    seen[n] += 1
    if n not in order:
        order.append(n)
        say(f"   saw: {n}")


lis = keyboard.Listener(on_press=on_press)
lis.daemon = True
lis.start()
time.sleep(20)
lis.stop()

say("")
say("-" * 62)
if not seen:
    say("RESULT: NO key events arrived. macOS is blocking this app.")
    say("        Grant Input Monitoring (and Accessibility), then Cmd-Q")
    say("        the terminal and run this again.")
else:
    say(f"RESULT: {sum(seen.values())} key events arrived. Monitoring WORKS.")
    say(f"        keys seen: {', '.join(order)}")
    if "cmd_r" in seen:
        say("        right command detected — the talk key is fine.")
    else:
        say("        NOTE: 'cmd_r' never appeared.")
        say("        Either you did not press it, or this keyboard does not")
        say("        report it separately. Pick one of the keys listed above")
        say("        and set mic.key in agent/config.json, e.g. <alt_r> or <f13>.")
say("-" * 62)
say(f"(saved to {LOG})")
out.close()
