# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — one file, three platforms.

The speech models are NOT bundled: they are about 6.6GB, well past what any
release can carry. `agent/fetch_models.py` pulls them on first run instead.

What IS bundled is everything small and essential: the agent's Python, the
face and setup pages, the vendored hand-tracking model, and the templates
that first-run setup renders CLAUDE.md and profile.md from.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP = "Lugalay"

# (source, destination-inside-the-bundle)
datas = [
    (os.path.join(ROOT, "agent", "config.default.json"), "agent"),
    (os.path.join(ROOT, "agent", "templates"), os.path.join("agent", "templates")),
    (os.path.join(ROOT, "agent", "face"), os.path.join("agent", "face")),
    (os.path.join(ROOT, "agent", "hands"), os.path.join("agent", "hands")),
    (os.path.join(ROOT, "agent", "eyes"), os.path.join("agent", "eyes")),
    # how he speaks each language, kept as files so it can be tuned by hand
    (os.path.join(ROOT, "agent", "voice", "prompts"),
     os.path.join("agent", "voice", "prompts")),
    (os.path.join(ROOT, "agent", "TROUBLESHOOTING.md"), "agent"),
    (os.path.join(ROOT, "README.md"), "."),
]
# top-level agent modules (app.py is the entry point, not data)
for name in ("bus.py", "setup.py", "fetch_models.py"):
    datas.append((os.path.join(ROOT, "agent", name), "agent"))

# the voice package, minus its virtualenv and its multi-gigabyte models
for name in ("voice.py", "tools.py", "requirements.txt", "mictest.py", "langtest.py",
             "tune_my.py", "keytest.py", "diagnose.sh"):
    src = os.path.join(ROOT, "agent", "voice", name)
    if os.path.exists(src):
        datas.append((src, os.path.join("agent", "voice")))

from PyInstaller.utils.hooks import collect_data_files
datas += collect_data_files("kokoro_onnx")
datas += collect_data_files("faster_whisper")
# Kokoro speaks English through espeak-ng, whose phoneme data is a directory of
# plain files that nothing imports — so PyInstaller never sees it, Kokoro fails
# to load in the bundle, and the English voice quietly drops to the OS one.
datas += collect_data_files("espeakng_loader", include_py_files=False)

hiddenimports = [
    "webview", "webview.platforms",
    "sounddevice", "soundfile", "numpy",
    "faster_whisper", "kokoro_onnx", "onnxruntime", "edge_tts",
    "speech_recognition",
    # the eyes import cv2 lazily, inside the function that needs it, so that a
    # machine without it still starts — which also means nothing static points
    # at it for PyInstaller to follow
    "cv2",
]
if sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa", "AppKit", "Foundation", "objc"]
elif sys.platform == "win32":
    hiddenimports += ["webview.platforms.edgechromium", "clr_loader", "pythonnet"]
else:
    hiddenimports += ["webview.platforms.gtk", "gi"]

a = Analysis(
    [os.path.join(ROOT, "agent", "app.py")],
    pathex=[os.path.join(ROOT, "agent")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # models are fetched at runtime; torch is only ever needed to convert the
    # Burmese model, in a throwaway environment
    excludes=["torch", "transformers", "tkinter", "matplotlib", "pytest"],
    noarchive=False,
)

# Strip legacy Intel binaries bundled inside third-party packages (e.g. speech_recognition/flac-*)
# so the application is 100% pure Apple Silicon native with no macOS Intel compatibility warnings.
a.binaries = [b for b in a.binaries if not any(x in b[0] for x in ("flac-mac", "flac-linux", "flac-win32"))]
a.datas = [d for d in a.datas if not any(x in d[0] for x in ("flac-mac", "flac-linux", "flac-win32", "pocketsphinx-data"))]

# Never ship captured frames. They are whatever the webcam was last pointed at
# — which on a developer's machine is a photo of the developer — and a release
# built from a working checkout would carry it to everyone who downloads it.
# The runtime writes frames to the user's own directory anyway, so nothing in
# the bundle is ever read.
a.datas = [d for d in a.datas
           if os.path.join("eyes", "frames") not in d[0]]

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP,
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window on any platform
    icon=os.path.join(ROOT, "packaging", "icon.icns") if sys.platform == "darwin"
         else (os.path.join(ROOT, "packaging", "icon.ico") if sys.platform == "win32"
               else None),
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name=APP,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon=os.path.join(ROOT, "packaging", "icon.icns"),
        bundle_identifier="com.lugalay.app",
        info_plist={
            "CFBundleName": APP,
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": os.environ.get("LUGALAY_VERSION", "1.0.0"),
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # without these the prompts never appear and capture silently
            # returns zeros, which looks exactly like broken hardware
            "NSMicrophoneUsageDescription":
                "Lugalay listens to you so it can answer out loud.",
            "NSCameraUsageDescription":
                "Lugalay uses the camera to track your hands on the board, and to take a single photo when you ask it to look at something. Nothing is streamed or recorded.",
        },
    )
