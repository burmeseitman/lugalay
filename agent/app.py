#!/usr/bin/env python3
"""Lugalay as a desktop app.

Double-clicking Lugalay.app lands here. No terminal window, no browser tab:
the face runs in a real native window (WKWebView) and everything it needs is
started underneath and torn down when the window closes.

Everything that used to scroll past in Terminal goes to agent/logs/app.log.
"""
import atexit, json, multiprocessing, os, signal, socket, subprocess, sys, threading, time
multiprocessing.freeze_support()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bus  # noqa: E402

# Packaged, __file__ points inside the read-only bundle — bus knows where the
# writable side is, and creates it if this is the first launch.
bus.ensure_home()
HOME = bus.HOME
CFG = bus.config()
LOGDIR = bus.LOGS
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "app.log")

# A .app has no stdout to speak of; keep a real log instead of losing it.
# encoding is not optional: everything Lugalay says goes through here, and
# most of it is Burmese. Windows would otherwise pick cp1252 and take the
# whole app down with a UnicodeEncodeError on the very first greeting.
_log = open(LOG, "a", buffering=1, encoding="utf-8", errors="replace")
sys.stdout = sys.stderr = _log
print(f"\n=== Lugalay started {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

THREADS = []
_shut = threading.Lock()
_done = []
face_port = 7317


def _load(name, path):
    """Import a file by path. agent/face/server.py and agent/hands/server.py
    are both called 'server', so plain imports would collide."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_in_thread(name, fn, argv=None):
    """Run a piece of the agent on a thread.

    These used to be child processes, which a frozen build cannot do — there
    is no interpreter to spawn — and which kept surviving as orphans when the
    app was killed. Threads die with the process, which is what we want.
    """
    def target():
        old = sys.argv
        if argv is not None:
            sys.argv = argv
        try:
            fn()
        except SystemExit:
            pass
        except Exception:
            import traceback
            print(f"[app] {name} stopped with an error:")
            traceback.print_exc()
        finally:
            sys.argv = old

    t = threading.Thread(target=target, daemon=True, name=name)
    t.start()
    THREADS.append((name, t))
    print(f"[app] started {name}")
    return t


def shutdown(*_):
    """Everything runs on daemon threads, so they end with the process. This
    only has to put the bus back and say so."""
    with _shut:
        if _done:
            return
        _done.append(True)
    try:
        bus.write("idle")
    except Exception:
        pass
    print("[app] stopped")


atexit.register(shutdown)

# webview.start() blocks inside a native Cocoa runloop, and Python only runs
# signal handlers between its own bytecodes — so a plain signal.signal handler
# never fires and the app ignores SIGTERM, orphaning the voice loop and the
# face server. Block the signals everywhere and wait for them on a thread of
# our own, which works no matter what the main thread is doing.
_SIGS = {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}
signal.pthread_sigmask(signal.SIG_BLOCK, _SIGS)


def _reaper():
    sig = signal.sigwait(_SIGS)
    print(f"[app] got signal {sig}, shutting down")
    shutdown()
    os._exit(0)


threading.Thread(target=_reaper, daemon=True).start()


def port_open(port, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def main():
    global face_port
    face_port = int(CFG.get("face_port", 7317))
    if not port_open(face_port):
        face_mod = _load("lugalay_face", bus.resource("face", "server.py"))
        run_in_thread("face", face_mod.main, argv=["server.py", "--no-open"])
        for _ in range(60):
            if port_open(face_port):
                break
            time.sleep(0.1)
    else:
        print(f"[app] face already on :{face_port}, reusing")

    hands_port = int(CFG.get("hands_port", 7318))
    if not port_open(hands_port):
        hands_mod = _load("lugalay_hands", bus.resource("hands", "server.py"))
        run_in_thread("hands", hands_mod.main, argv=["server.py", "--no-open"])
    else:
        print(f"[app] hands already on :{hands_port}, reusing")

    def start_voice():
        if any(n == "voice" for n, _ in THREADS):
            return
        voice_mod = _load("lugalay_voice", bus.resource("voice", "voice.py"))
        run_in_thread("voice", voice_mod.main, argv=["voice.py"])

    # a fresh install does not know who it is talking to yet: ask before
    # starting the microphone, so the greeting can use their actual name
    first_run = not bus.config().get("setup_done")

    # Repair an install that was set up before these files were written to the
    # right place. Setup used to resolve HOME from its own location, which in a
    # packaged build is inside the read-only bundle, so CLAUDE.md, the memory
    # profile and the permission allowlist never reached the user's directory —
    # leaving a Lugalay with no personality and no permission to do anything.
    # Only writes what is missing, so nothing anyone has edited is touched.
    if not first_run:
        missing = [f for f in ("CLAUDE.md", os.path.join(".claude", "settings.json"),
                               os.path.join("memory", "profile.md"))
                   if not os.path.exists(os.path.join(bus.HOME, f))]
        if missing:
            try:
                cfg = bus.config()
                setup_mod = _load("lugalay_setup", bus.resource("setup.py"))
                wrote = setup_mod.render(cfg.get("user", ""), cfg.get("name", "Lugalay"))
                print(f"[app] repaired missing {missing} -> wrote {wrote}")
            except Exception as e:
                print(f"[app] could not repair {missing}: {e}")
    if not first_run:
        start_voice()

    import webview

    class Api:
        """Bridge for things only the native window can do.

        WKWebView ships with the DOM Fullscreen API switched off, so
        document.requestFullscreen() silently does nothing inside the app —
        the page has to ask the real window instead.
        """

        def __init__(self):
            self.window = None

        def toggle_fullscreen(self):
            if self.window:
                self.window.toggle_fullscreen()
            return True

        def minimize(self):
            if self.window:
                self.window.minimize()
            return True

        def quit(self):
            shutdown()
            os._exit(0)

        def set_on_top(self, flag):
            """An overlay avatar is only useful if it stays visible."""
            if self.window:
                self.window.on_top = bool(flag)
            return True

        def setup_finished(self):
            """First run is over: start listening and show the face."""
            start_voice()
            if self.window:
                self.window.load_url(f"http://127.0.0.1:{face_port}/")
            return True

    api = Api()
    win = CFG.get("window", {})
    window = webview.create_window(
        CFG.get("name", "Lugalay"),
        f"http://127.0.0.1:{face_port}/" + ("setup" if first_run else ""),
        width=int(win.get("width", 460)),
        height=int(win.get("height", 640)),
        x=win.get("x"), y=win.get("y"),
        resizable=True,
        # Transparency and framelessness can only be chosen when the window is
        # created, so the window is always transparent and the PAGE paints its
        # own dark card. Hiding that card is what makes overlay mode possible
        # at the press of a key.
        frameless=bool(win.get("frameless", True)),
        easy_drag=True,
        transparent=bool(win.get("transparent", True)),
        on_top=bool(win.get("always_on_top", False)),
        background_color=win.get("background_color", "#04070A"),
        js_api=api,
    )
    api.window = window

    def clear_webview_background():
        """Make WKWebView stop painting its own opaque backdrop.

        pywebview sets 'drawsTransparentBackground', which is the old WebView
        key — WKWebView ignores it, so the window is transparent but the view
        on top of it is not. There is no single reliable switch across macOS
        versions, so try all of them and report which ones took.
        """
        if sys.platform != "darwin":
            # pywebview handles transparency itself on Windows (EdgeChromium)
            # and Linux (GTK); only WKWebView needs the manual nudge.
            print("[app] transparency: handled by the platform backend")
            return
        results = []
        try:
            from webview.platforms.cocoa import BrowserView
            from AppKit import NSColor
        except Exception as e:
            print(f"[app] transparency: cannot reach the native window: {e}")
            return

        for bv in BrowserView.instances.values():
            wv, win = bv.webview, bv.window
            # 1. the private key that has worked for years
            try:
                wv.setValue_forKey_(False, "drawsBackground")
                results.append("drawsBackground=False")
            except Exception as e:
                results.append(f"drawsBackground FAILED({type(e).__name__})")
            # 2. the modern, public API (macOS 12+)
            try:
                wv.setUnderPageBackgroundColor_(NSColor.clearColor())
                results.append("underPageBackgroundColor=clear")
            except Exception as e:
                results.append(f"underPageBackgroundColor FAILED({type(e).__name__})")
            # 3. the layer underneath, which can stay opaque on its own
            try:
                wv.setWantsLayer_(True)
                layer = wv.layer()
                if layer is not None:
                    layer.setOpaque_(False)
                    layer.setBackgroundColor_(NSColor.clearColor().CGColor())
                    results.append("layer=clear")
            except Exception as e:
                results.append(f"layer FAILED({type(e).__name__})")
            # 4. and the window itself
            try:
                win.setOpaque_(False)
                win.setHasShadow_(False)
                win.setBackgroundColor_(NSColor.clearColor())
                results.append("window=clear")
            except Exception as e:
                results.append(f"window FAILED({type(e).__name__})")

        print("[app] transparency: " + ", ".join(results) if results
              else "[app] transparency: no windows found")

    window.events.loaded += clear_webview_background
    window.events.closed += lambda: shutdown()
    webview.start()          # blocks on the main thread until the window closes


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
