"""The bus: the entire integration between Lugalay's pieces.

The voice writes a small JSON file; the face and hands read it. That is all.
No sockets, no broker, no framework — a file that any of them can survive
the others not existing.
"""
import json, os, sys, tempfile, time, urllib.parse

# ── where things live ─────────────────────────────────────────────────────
# Running from a checkout, everything sits together in the repo. Packaged,
# the bundle is read-only, so anything written at runtime — the config with
# the person's name, the memory vault, the downloaded models, the logs — has
# to live in the user's own directory instead.
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    RESOURCES = os.path.join(sys._MEIPASS, "agent")      # read-only, in the app
    HOME = os.path.join(os.path.expanduser("~"), "Lugalay")
    ROOT = os.path.join(HOME, "agent")                   # writable
else:
    RESOURCES = os.path.dirname(os.path.abspath(__file__))
    ROOT = RESOURCES
    HOME = os.path.dirname(ROOT)

BUS = os.path.join(ROOT, "bus", "state.json")
FACE = os.path.join(ROOT, "bus", "face.json")
CONFIG = os.path.join(ROOT, "config.json")
LOGS = os.path.join(ROOT, "logs")
MODELS = os.path.join(ROOT, "voice", "models")


def resource(*parts):
    """A file that ships with the app and is never written to."""
    return os.path.join(RESOURCES, *parts)


def ensure_home():
    """Create the writable side on first launch of a packaged build."""
    prompts_dir = os.path.join(ROOT, "voice", "prompts")
    for d in (ROOT, os.path.dirname(BUS), LOGS, MODELS,
              os.path.join(HOME, "memory"), prompts_dir):
        os.makedirs(d, exist_ok=True)
    # Seed default prompt files so the user can easily customize and add words
    for name in ("burmese_terms.txt", "spoken_burmese.md"):
        dest = os.path.join(prompts_dir, name)
        src = resource("voice", "prompts", name)
        if not os.path.exists(dest) and os.path.exists(src):
            try:
                import shutil
                shutil.copy2(src, dest)
            except OSError:
                pass
    return HOME

# ── who is allowed to talk to the local servers ───────────────────────────
# Both servers listen on the loopback address, which sounds private but is not:
# every page in the person's browser can reach 127.0.0.1 too. Without a check
# here, any website he visited could POST to /open and put a page of its own
# choosing on his screen, or to /look and take a photo with his webcam.
#
# Browsers label their own requests. Sec-Fetch-Site says where a request came
# from and is sent on everything, including <img> and <script>; Origin is sent
# on POSTs and on cross-origin fetches. A page on the internet therefore
# announces itself and can be turned away. Things that are not browsers —
# curl, urllib, Lugalay's own tools — send neither header, and those are the
# callers these servers exist to serve.
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")


def local_request(headers, port):
    """True if this request may be acted on. False for anything cross-site."""
    # 1. Host must still be us. A name that resolves to 127.0.0.1 — the DNS
    #    rebinding trick — arrives with the attacker's hostname in this header.
    host = (headers.get("Host") or "").strip()
    if host:
        try:
            hostname = urllib.parse.urlsplit("//" + host).hostname
        except ValueError:
            return False
        if hostname not in LOCAL_HOSTS:
            return False

    # 2. A browser telling us it came from somewhere else is telling the truth.
    site = (headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site and site not in ("same-origin", "none"):
        return False

    # 3. And if it named an origin, that origin has to be this very server.
    origin = (headers.get("Origin") or "").strip()
    if origin and origin.lower() != "null":
        try:
            u = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        if u.hostname not in LOCAL_HOSTS:
            return False
        if (u.port or (443 if u.scheme == "https" else 80)) != port:
            return False
    return True


def save_config(cfg):
    """Write config.json without ever leaving it half-written.

    It holds the person's name, his settings and his API key, and both the
    settings page and the voice loop write it. A plain open(w) truncates first,
    so a crash or a second writer arriving mid-write loses the lot.
    """
    ensure_home()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CONFIG), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        # the API key lives in here; nobody else on the machine needs to read it
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG)
    except BaseException:
        os.path.exists(tmp) and os.unlink(tmp)
        raise
    return cfg


VALID = ("idle", "listening", "thinking", "speaking", "error")


DEFAULT_CONFIG = os.path.join(RESOURCES, "config.default.json")


def config():
    """The live settings.

    config.json is personal — it holds the person's name — so it is not in
    version control. On a fresh clone it is created from the defaults, which
    have setup_done false, so the app asks who it is talking to.
    """
    if not os.path.exists(CONFIG) and os.path.exists(DEFAULT_CONFIG):
        ensure_home()
        with open(DEFAULT_CONFIG, encoding="utf-8") as f:
            seed = f.read()
        with open(CONFIG, "w", encoding="utf-8") as f:
            f.write(seed)
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def read():
    try:
        with open(BUS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"state": "idle", "text": "", "level": 0.0, "ts": time.time()}


def write(state, text="", level=0.0):
    """Atomic write — the face polls this file constantly and must never
    catch it half-written."""
    if state not in VALID:
        raise ValueError(f"unknown state {state!r}")
    os.makedirs(os.path.dirname(BUS), exist_ok=True)
    payload = {"state": state, "text": text, "level": round(float(level), 4),
               "ts": time.time()}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(BUS), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, BUS)
    except BaseException:
        os.path.exists(tmp) and os.unlink(tmp)
        raise
    return payload


# ── which persona is on screen ─────────────────────────────────────────────
# The state file flows voice -> face. This one flows the other way: the person
# presses 1-5 on the face and the voice has to pick up the matching voice.

def faces():
    return config().get("faces", [])


def face_id():
    """The persona currently selected, falling back to the configured default."""
    try:
        with open(FACE, encoding="utf-8") as f:
            wanted = json.load(f).get("id")
    except (OSError, ValueError):
        wanted = None
    ids = [f["id"] for f in faces()]
    if wanted in ids:
        return wanted
    default = config().get("face")
    return default if default in ids else (ids[0] if ids else None)


def face():
    """The full persona dict for the selected face."""
    fid = face_id()
    for f in faces():
        if f["id"] == fid:
            return f
    return {}


def set_face(fid):
    if fid not in [f["id"] for f in faces()]:
        raise ValueError(f"unknown face {fid!r}")
    os.makedirs(os.path.dirname(FACE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(FACE), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"id": fid, "ts": time.time()}, f)
    os.replace(tmp, FACE)
    return fid
