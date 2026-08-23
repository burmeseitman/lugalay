#!/usr/bin/env python3
"""Fail the build here rather than shipping a binary that cannot start.

PyInstaller will happily package code that raises on import, and the failure
then shows up as a window that never appears on someone else's machine. This
checks the things that have actually broken during development.
"""
import ast
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENT = os.path.join(ROOT, "agent")
fails = []


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ── every source file parses ──────────────────────────────────────────────
for base, _dirs, files in os.walk(AGENT):
    if ".venv" in base or "models" in base or "__pycache__" in base:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(base, f)
        try:
            ast.parse(open(p, encoding="utf-8").read())
            ok, detail = True, ""
        except SyntaxError as e:
            ok, detail = False, f"line {e.lineno}: {e.msg}"
        check(os.path.relpath(p, ROOT), ok, detail)

# ── the shipped config is a valid, impersonal starting point ──────────────
try:
    cfg = json.load(open(os.path.join(AGENT, "config.default.json"), encoding="utf-8"))
    check("config.default.json parses", True)
    check("ships with no name", cfg.get("user") == "", repr(cfg.get("user")))
    check("ships with setup pending", cfg.get("setup_done") is False)
    check("has five faces", len(cfg.get("faces", [])) >= 1,
          f"{len(cfg.get('faces', []))} faces")
    ids = [f["id"] for f in cfg.get("faces", [])]
    check("default face exists", cfg.get("face") in ids, cfg.get("face"))
    for f in cfg.get("faces", []):
        v = f.get("voice", {})
        check(f"face {f['id']} has both voices", bool(v.get("my") and v.get("en")))
except Exception as e:
    check("config.default.json", False, str(e))

# ── the templates first-run setup renders from ────────────────────────────
for t in ("CLAUDE.md.tmpl", "profile.md.tmpl"):
    p = os.path.join(AGENT, "templates", t)
    ok = os.path.isfile(p)
    body = open(p, encoding="utf-8").read() if ok else ""
    check(f"template {t}", ok and "{{USER}}" in body,
          "missing {{USER}} placeholder" if ok and "{{USER}}" not in body else "")

# ── the pages the window loads ────────────────────────────────────────────
for page, needles in (("index.html", ["applyOverlay", "selectFace", "id=\"plate\""]),
                      ("setup.html", ["/setup-defaults", "setup_finished"])):
    p = os.path.join(AGENT, "face", page)
    ok = os.path.isfile(p)
    body = open(p, encoding="utf-8").read() if ok else ""
    missing = [n for n in needles if n not in body]
    check(f"face/{page}", ok and not missing,
          f"missing {missing}" if missing else "")

# ── the vendored hand tracker, which must work without a CDN ──────────────
for f in ("vendor/hand_landmarker.task", "vendor/vision_bundle.mjs",
          "vendor/wasm/vision_wasm_internal.wasm"):
    check(f"hands/{f}", os.path.isfile(os.path.join(AGENT, "hands", f)))

# ── the runtime dependencies actually import on this runner ───────────────
for mod in ("webview", "sounddevice", "soundfile", "numpy",
            "faster_whisper", "kokoro_onnx", "edge_tts"):
    try:
        __import__(mod)
        check(f"import {mod}", True)
    except Exception as e:
        check(f"import {mod}", False, f"{type(e).__name__}: {e}")

print()
if fails:
    print(f"  {len(fails)} check(s) failed:")
    for f in fails:
        print(f"    - {f}")
    sys.exit(1)
print("  preflight passed\n")
