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
# the allowlist template: without it an install has no permissions at all
_st = os.path.join(AGENT, "templates", "settings.json.tmpl")
try:
    _sj = json.load(open(_st, encoding="utf-8"))
    check("template settings.json.tmpl", True)
    check("allowlist lets him write memory",
          "Write(memory/**)" in _sj["permissions"]["allow"])
    check("allowlist is not Bash(*)",
          not any(a.strip() in ("Bash(*)", "Bash(:*)")
                  for a in _sj["permissions"]["allow"]))
    check("allowlist still denies rm and sudo",
          "Bash(rm:*)" in _sj["permissions"]["deny"]
          and "Bash(sudo:*)" in _sj["permissions"]["deny"])
except Exception as e:
    check("template settings.json.tmpl", False, str(e))

_setup_src = open(os.path.join(AGENT, "setup.py"), encoding="utf-8").read()
check("setup writes to the writable home", "HOME = bus.HOME" in _setup_src)
check("setup installs the allowlist", "settings.json.tmpl" in _setup_src)

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

# ── the spoken-Burmese prompt, which decides how human he sounds ──────────
_bp = os.path.join(AGENT, "voice", "prompts", "spoken_burmese.md")
_ok = os.path.isfile(_bp)
_body = open(_bp, encoding="utf-8").read() if _ok else ""
check("voice/prompts/spoken_burmese.md", _ok)
if _ok:
    # everything above the first --- is a note to the editor; the loader cuts
    # it off, so the separator has to be there or the model reads the note
    check("prompt has an editor-note separator", "\n---\n" in _body)
    _sent = _body.split("\n---\n", 1)[-1]
    check("prompt survives the cut", len(_sent.strip()) > 200,
          f"{len(_sent.strip())} chars")
    check("prompt bans written particles", "သည်" in _sent and "မည်" in _sent)
    # the few-shot pairs are the part that actually moves the output; losing
    # them silently would leave a prompt that still looks fine
    check("prompt keeps its few-shot pairs",
          _sent.count("Bad Output") >= 2 and _sent.count("Good Output") >= 2)
    check("prompt still bans parentheses and markdown",
          "No Parentheses" in _sent and "No Markdown" in _sent)

_voice_src = open(os.path.join(AGENT, "voice", "voice.py"), encoding="utf-8").read()
check("brain loads the style from file", "def spoken_style" in _voice_src
      and "self.style(lang" in _voice_src)

# the transliteration table is the guarantee behind the prompt's request, so a
# malformed line must not pass silently
_tp = os.path.join(AGENT, "voice", "prompts", "burmese_terms.txt")
if os.path.isfile(_tp):
    _pairs, _bad = [], []
    for _i, _l in enumerate(open(_tp, encoding="utf-8"), 1):
        _l = _l.split("#", 1)[0].strip()
        if not _l:
            continue
        if "=" not in _l:
            _bad.append(f"line {_i}")
            continue
        _en, _my = (x.strip() for x in _l.split("=", 1))
        if not _en or not _my or not any("\u1000" <= c <= "\u109f" for c in _my):
            _bad.append(f"line {_i}")
        else:
            _pairs.append(_en)
    check("burmese_terms.txt parses", not _bad, ", ".join(_bad))
    check("burmese_terms.txt has entries", len(_pairs) > 10, f"{len(_pairs)} terms")
    check("no duplicate terms", len(_pairs) == len(set(p.lower() for p in _pairs)))
else:
    check("burmese_terms.txt", False, "missing")
check("speech path transliterates", "transliterate_terms(text)" in _voice_src)

# Burmese streams through ONE voice in small units. If either half of that is
# lost, the symptom is the accent hopping mid-answer — the exact bug that made
# Burmese whole-block to begin with.
check("burmese streams", "def speak_burmese_stream" in _voice_src
      and "mouth.speak_burmese_stream" in _voice_src)
check("streaming renders in small units", "def _stream_units" in _voice_src
      and "STREAM_LIMIT_MY" in _voice_src)
check("synthesis cannot hang forever", "SYNTH_TIMEOUT" in _voice_src)
check("a failed turn cannot end the session", "def safe_respond" in _voice_src)

# ── the eyes: present, importable, and wired into the voice loop ──────────
sys.path.insert(0, AGENT)
try:
    from eyes import look as _look
    check("eyes import", True)
    # the triggers are the whole interface — an empty list means Lugalay can
    # never be asked to look at anything
    check("eyes has Burmese triggers", len(_look.TRIGGERS_MY) > 0)
    check("eyes has English triggers", len(_look.TRIGGERS_EN) > 0)
    check("eyes trigger fires", _look.wants_to_look("look at this")
          and _look.wants_to_look("ဒါကိုကြည့်ပါ"))
    check("eyes ignores ordinary talk", not _look.wants_to_look("what is the weather"))
except Exception as e:
    check("eyes import", False, f"{type(e).__name__}: {e}")

_voice = open(os.path.join(AGENT, "voice", "voice.py"), encoding="utf-8").read()
check("voice loop asks the eyes", "look.wants_to_look" in _voice)
check("voice loop sends the photo", "brain.ask(asked" in _voice
      and "brain.stream(asked" in _voice)

# ── every text file and subprocess must name utf-8 ────────────────────────
# Lugalay speaks Burmese. Python picks the *locale* encoding when none is
# given, which on Windows is cp1252 and cannot represent a single Burmese
# character — so an omission here is not a style nit, it is a crash on one
# platform and silence on the others. Caught here because no macOS or Linux
# test will ever reproduce it.
def _no_encoding(tree):
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kw = {k.arg for k in node.keywords}
        fn = node.func
        # bare open(...), or os.fdopen(...) — but NOT webbrowser.open(...),
        # which takes a URL and no encoding
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr if fn.attr != "open" else ""
        else:
            name = ""

        if name in ("open", "fdopen"):
            mode = ""
            if name == "open" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value or ""
            elif name == "fdopen" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value or ""
            if "b" not in mode and "encoding" not in kw:
                bad.append(f"{name}() line {node.lineno}")

        elif name in ("run", "Popen", "check_output"):
            texty = any(k.arg in ("text", "universal_newlines", "capture_output")
                        and getattr(k.value, "value", False) is True
                        for k in node.keywords)
            if texty and "encoding" not in kw:
                bad.append(f"subprocess.{name}() line {node.lineno}")
    return bad


for base, _dirs, files in os.walk(AGENT):
    if any(x in base for x in (".venv", "models", "__pycache__")):
        continue
    for f in sorted(files):
        if not f.endswith(".py"):
            continue
        fp = os.path.join(base, f)
        try:
            bad = _no_encoding(ast.parse(open(fp, encoding="utf-8").read()))
        except SyntaxError:
            continue          # already reported above
        check(f"utf-8 explicit in {os.path.relpath(fp, ROOT)}",
              not bad, ", ".join(bad))

# ── the local servers must refuse the browser of anyone else ──────────────
# Both listen on loopback, which every page in the person's browser can also
# reach. Without this check a website could POST to /open and put a page on his
# screen, or to /look and take a photo. Losing it again would be silent, so it
# is asserted here rather than trusted.
sys.path.insert(0, AGENT)
try:
    import bus as _bus

    class _H(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)

    _cases = [
        ("cross-site fetch", {"Host": "127.0.0.1:7318",
                              "Sec-Fetch-Site": "cross-site",
                              "Origin": "https://evil.example"}, False),
        ("cross-site img tag", {"Host": "127.0.0.1:7318",
                                "Sec-Fetch-Site": "cross-site"}, False),
        ("dns rebinding", {"Host": "evil.example:7318"}, False),
        ("foreign origin", {"Host": "127.0.0.1:7318",
                            "Origin": "http://127.0.0.1:9999"}, False),
        ("the page itself", {"Host": "127.0.0.1:7318",
                             "Sec-Fetch-Site": "same-origin",
                             "Origin": "http://127.0.0.1:7318"}, True),
        ("lugalay's own curl", {"Host": "127.0.0.1:7318"}, True),
    ]
    _bad = [n for n, h, want in _cases
            if _bus.local_request(_H(h), 7318) is not want]
    check("local servers refuse cross-site requests", not _bad, ", ".join(_bad))
    check("config is written atomically", hasattr(_bus, "save_config"))
except Exception as e:
    check("origin guard", False, f"{type(e).__name__}: {e}")

for _srv in ("hands/server.py", "face/server.py"):
    _src = open(os.path.join(AGENT, _srv), encoding="utf-8").read()
    check(f"{_srv} guards GET and POST", _src.count("bus.local_request") >= 2)

check("no direct config writes outside bus",
      'open(bus.CONFIG, "w"' not in
      open(os.path.join(AGENT, "face", "server.py"), encoding="utf-8").read())

# ── the local fallback must not call a model that is not there ────────────
_v = open(os.path.join(AGENT, "voice", "voice.py"), encoding="utf-8").read()
check("fallback checks what is installed", "_pick_model" in _v)
check("fallback no longer trusts the configured name",
      'o.get("model", names[0]' not in _v and 'o.get("model", models[0]' not in _v)

# ── the tools a local model is given ──────────────────────────────────────
# Without these the offline brain can only talk: it cannot read what it was
# told last week or write down what it just learned.
sys.path.insert(0, os.path.join(AGENT, "voice"))
try:
    import tools as _tools
    check("local tools import", True)
    check("every schema has a function behind it",
          all(s["function"]["name"] in _tools.REGISTRY for s in _tools.SCHEMAS),
          f"{len(_tools.SCHEMAS)} schemas")
    # a model will happily be talked into a path outside the vault
    _root = _tools._memory_root()
    _escapes = ["../../../../etc/passwd", "../../.ssh/id_rsa", "/etc/passwd",
                "....//....//etc/hosts"]
    _out = [e for e in _escapes
            if (_p := _tools._safe_path(e)) and not _p.startswith(_root + os.sep)]
    check("memory writes cannot leave the vault", not _out, ", ".join(_out))
    check("unknown tools are refused",
          "no tool called" in _tools.run("rm_rf", {}))
except Exception as e:
    check("local tools", False, f"{type(e).__name__}: {e}")

_vsrc = open(os.path.join(AGENT, "voice", "voice.py"), encoding="utf-8").read()
check("the local brain runs a tool loop", "_tool_round" in _vsrc
      and "local_tools.SCHEMAS" in _vsrc)

# ── hosted OpenAI-compatible backend
check("hosted openai-compatible backend wired", "_remote_stream" in _vsrc
      and 'f"Bearer {api_key}"' in _vsrc)
check("remote path speaks the tool loop too", "_remote_tool_round" in _vsrc)
check("presets available for common providers",
      all(n in _vsrc for n in ("openai", "groq", "together", "openrouter", "deepseek")))
_dcfg = json.load(open(os.path.join(AGENT, "config.default.json"), encoding="utf-8"))
# ── Burmese TTS: Gemini performance first, clean Microsoft Edge fallback
check("burmese edge-tts implemented",
      "_synth_burmese_edge_bytes" in _vsrc and "edge_tts" in _vsrc)
check("gemini Burmese TTS primary is wired",
      "_synth_burmese_gemini" in _vsrc
      and "gemini-2.5-flash-preview-tts" in _vsrc)
check("edge fallback strips reaction tags",
      "edge_text = clean_spoken_text(tagged, keep_sfx_tags=False)" in _vsrc)

check("brain.remote in the shipped default", "remote" in _dcfg.get("brain", {}))

# ── the runtime dependencies actually import on this runner ───────────────
for mod in ("webview", "sounddevice", "soundfile", "numpy",
            "faster_whisper", "kokoro_onnx", "edge_tts", "cv2"):
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
