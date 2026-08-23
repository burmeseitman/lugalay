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
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bus  # noqa: E402

TEMPLATES = os.path.join(HERE, "templates")


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
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
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
            ("profile.md.tmpl", os.path.join(HOME, "memory", "profile.md"))]
    for tmpl, dest in jobs:
        src = os.path.join(TEMPLATES, tmpl)
        if not os.path.isfile(src):
            continue
        if os.path.exists(dest):
            backup = dest + ".before-setup"
            if not os.path.exists(backup):
                with open(dest, encoding="utf-8") as f:
                    old = f.read()
                with open(backup, "w", encoding="utf-8") as f:
                    f.write(old)
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
    user = (answers.get("user") or "").strip() or detect_name() or "friend"
    agent = (answers.get("agent") or cfg.get("name") or "Lugalay").strip()
    listen_lang = answers.get("listen_language") or "my"
    speak_lang = answers.get("speak_language") or answers.get("language") or "my"
    face = answers.get("face") or cfg.get("face")

    cfg["user"] = user
    cfg["name"] = agent
    cfg.setdefault("language", {})["listen"] = listen_lang
    cfg.setdefault("language", {})["reply"] = speak_lang
    if "api_key" in answers:
        key = (answers.get("api_key") or "").strip()
        if key and not key.startswith("•"):
            cfg.setdefault("tts", {})["api_key"] = key
    if face in [f["id"] for f in cfg.get("faces", [])]:
        cfg["face"] = face
        try:
            bus.set_face(face)
        except Exception:
            pass
    cfg["setup_done"] = True

    with open(bus.CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

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
