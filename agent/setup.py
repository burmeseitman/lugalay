#!/usr/bin/env python3
"""First run: find out who this is, and write the agent around them.

The name used to be baked into config.json, CLAUDE.md and memory/profile.md,
so a second person installing this would be greeted by someone else's name
forever. Everything the person tells us lands in config.json, and the two
markdown files are rendered from agent/templates/ so they stay in step.

    python3 setup.py                 interactive, in a terminal
    python3 setup.py --detect        print what macOS thinks the name is
    python3 setup.py --apply '{...}' apply a JSON answer set (used by the app)
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bus  # noqa: E402

# bus knows the difference between the code and the writable side. Taking HOME
# from the file's own location put CLAUDE.md and profile.md *inside the app
# bundle* in a packaged build — read-only, and never read again — so the
# installed Lugalay came up with no personality and no memory at all.
HOME = bus.HOME
TEMPLATES = bus.resource("templates")

# Maximum length for user/agent names to prevent abuse via /setup.
_NAME_MAX = 40
# Allow letters (any script), digits, spaces, hyphens, apostrophes, and dots.
# Strip everything else — especially newlines, braces, and control characters
# that could corrupt CLAUDE.md or .claude/settings.json templates.
_NAME_RE = re.compile(r"[^\w\s\-'.]+", re.UNICODE)


def _sanitize_name(raw):
    """Clean a user or agent name for safe template interpolation."""
    cleaned = _NAME_RE.sub("", raw).strip()
    return cleaned[:_NAME_MAX] or "friend"


def set_gemini_api_key(cfg, value=None, clear=False):
    """Safely update the saved Gemini key without ever returning or logging it."""
    tts = cfg.setdefault("tts", {})
    if clear:
        tts.pop("gemini_api_key", None)
        # Clear the legacy field too, otherwise it would silently remain active.
        tts["api_key"] = ""
        return False
    if value is None:
        return bool(tts.get("gemini_api_key") or tts.get("api_key"))

    key = str(value).strip()
    if not key or key.startswith("•"):
        return bool(tts.get("gemini_api_key") or tts.get("api_key"))
    if len(key) > 512 or any(ch.isspace() or ord(ch) < 32 for ch in key):
        raise ValueError("Gemini API key must be a single value without spaces")

    # New writes use an explicit provider-specific field. Remove the old
    # generic copy so the secret exists only once in the owner-only config.
    tts["gemini_api_key"] = key
    tts["api_key"] = ""
    return True


def detect_name():
    """The account's full name is a decent guess, never an assumption."""
    if sys.platform == "darwin":
        cmds = [["id", "-F"],
                ["dscl", ".", "-read", f"/Users/{os.environ.get('USER','')}", "RealName"]]
    elif sys.platform == "win32":
        cmds = [["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_UserAccount -Filter "
                 "\"Name='$env:USERNAME'\").FullName"]]
    else:  # linux and friends: the GECOS field
        cmds = [["getent", "passwd", os.environ.get("USER", "")]]

    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if cmd[0] == "getent":
            parts = out.split(":")
            out = parts[4].split(",")[0] if len(parts) > 4 else ""
        out = out.replace("RealName:", " ")
        name = " ".join(n.strip() for n in out.splitlines() if n.strip())
        if name:
            return name
    return (os.environ.get("USER") or os.environ.get("USERNAME") or "").title()


def render(user, agent="Lugalay", agent_my="လူကလေး"):
    """Write CLAUDE.md and memory/profile.md for this person.

    Never clobbers an existing CLAUDE.md: someone re-running setup should not
    lose the personality they have been editing.
    """
    written = []
    jobs = [("CLAUDE.md.tmpl", os.path.join(HOME, "CLAUDE.md")),
            ("profile.md.tmpl", os.path.join(HOME, "memory", "profile.md")),
            # Without this the installed Lugalay has no allowlist at all, and a
            # spoken session cannot approve anything — so he could not even
            # write to his own memory, and every request to do something ended
            # in a refusal nobody could grant.
            ("settings.json.tmpl", os.path.join(HOME, ".claude", "settings.json"))]
    for tmpl, dest in jobs:
        src = os.path.join(TEMPLATES, tmpl)
        if not os.path.isfile(src):
            continue
        if os.path.exists(dest):
            backup = dest + ".before-setup"
            try:
                with open(dest, encoding="utf-8") as f:
                    old = f.read()
                with open(backup, "w", encoding="utf-8") as f:
                    f.write(old)
            except OSError:
                pass
        with open(src, encoding="utf-8") as f:
            body = f.read()
        body = (body.replace("{{USER}}", user)
                    .replace("{{AGENT_MY}}", agent_my)
                    .replace("{{AGENT}}", agent))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(body)
        written.append(os.path.relpath(dest, HOME))
    return written


def apply(answers):
    """answers: {user, agent, listen_language, speak_language, language, face}. Returns a summary dict."""
    cfg = bus.config()
    user = _sanitize_name((answers.get("user") or "").strip() or detect_name() or "friend")
    agent = _sanitize_name((answers.get("agent") or cfg.get("name") or "Lugalay").strip())
    listen_lang = answers.get("listen_language") or "my"
    speak_lang = answers.get("speak_language") or answers.get("language") or "my"
    face = answers.get("face") or cfg.get("face")

    cfg["user"] = user
    cfg["name"] = agent
    cfg.setdefault("language", {})["listen"] = listen_lang
    cfg.setdefault("language", {})["reply"] = speak_lang
    if "gemini_api_key" in answers or "api_key" in answers:
        set_gemini_api_key(
            cfg, answers.get("gemini_api_key", answers.get("api_key")))
    if face in [f["id"] for f in cfg.get("faces", [])]:
        cfg["face"] = face
        try:
            bus.set_face(face)
        except Exception:
            pass
    cfg["setup_done"] = True

    bus.save_config(cfg)

    files = render(user, agent)
    return {"user": user, "agent": agent, "listen_language": listen_lang,
            "speak_language": speak_lang, "face": cfg.get("face"), "files": files}


def interactive():
    cfg = bus.config()
    guess = detect_name()
    print(f"\n  Setting up your assistant.\n")
    user = input(f"  What should it call you? [{guess}] ").strip() or guess
    agent = input(f"  What is the assistant called? [{cfg.get('name','Lugalay')}] ").strip() \
        or cfg.get("name", "Lugalay")
    lang = input("  Reply in Burmese or English? [my/en, default my] ").strip().lower()
    lang = "en" if lang.startswith("e") else "my"
    out = apply({"user": user, "agent": agent, "language": lang})
    print(f"\n  Done. {out['agent']} will call you {out['user']}.")
    print(f"  Wrote: {', '.join(out['files'])}\n")
    return 0


def main():
    if "--detect" in sys.argv:
        print(detect_name())
        return 0
    if "--apply" in sys.argv:
        i = sys.argv.index("--apply")
        answers = json.loads(sys.argv[i + 1]) if len(sys.argv) > i + 1 else {}
        print(json.dumps(apply(answers), ensure_ascii=False))
        return 0
    return interactive()


if __name__ == "__main__":
    sys.exit(main())
