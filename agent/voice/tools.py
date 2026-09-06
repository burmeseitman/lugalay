#!/usr/bin/env python3
"""The tools a local model is given.

Claude arrives with its own tools; a local model arrives with none, so until
now the offline brain could only talk. It could not read a thing it had been
told last week, could not write down what it had just learned, and could not
put a page on the screen — which is most of what Lugalay is for.

Every tool here is deliberately narrow. A model is not shell access: it gets
the four verbs it actually needs, each one validated on this side, and the two
that touch the machine go through the same checked endpoints Claude uses.
"""
import glob, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bus  # noqa: E402

MAX_READ = 4000            # characters handed back from the vault in one go
MAX_NOTE = 2000            # characters a model may write in one note
TIMEOUT = 8


def _memory_root():
    root = os.path.join(bus.HOME, "memory")
    os.makedirs(root, exist_ok=True)
    return os.path.realpath(root)


def _safe_path(name):
    """Resolve a vault-relative name, refusing anything that escapes it.

    A model asked to remember something will happily be talked into a filename
    like ../../.ssh/id_rsa, so the check is on the resolved path rather than on
    the string it was given.
    """
    root = _memory_root()
    name = (name or "").strip().lstrip("/")
    if not name:
        return None
    if not name.endswith(".md"):
        name += ".md"
    full = os.path.realpath(os.path.join(root, name))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


# ── the tools themselves ──────────────────────────────────────────────────

def read_memory(topic=""):
    """Return the parts of the vault that mention `topic`."""
    root = _memory_root()
    files = sorted(glob.glob(os.path.join(root, "**", "*.md"), recursive=True))
    if not files:
        return "The memory vault is empty."
    topic = (topic or "").strip().lower()
    out, total = [], 0
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            continue
        if topic and topic not in body.lower() and topic not in os.path.basename(f).lower():
            continue
        rel = os.path.relpath(f, root)
        chunk = body.strip()[:1200]
        if not chunk:
            continue
        out.append(f"--- {rel} ---\n{chunk}")
        total += len(chunk)
        if total > MAX_READ:
            break
    if not out:
        return f"Nothing in the vault mentions {topic!r}."
    return "\n\n".join(out)[:MAX_READ]


def remember(note, file="daily"):
    """Append a note to the vault. Defaults to today's daily page."""
    note = (note or "").strip()[:MAX_NOTE]
    if not note:
        return "Nothing to write."
    is_daily = file in ("daily", "", None)
    if is_daily:
        import datetime
        now = datetime.datetime.now()
        file = "daily/" + now.date().isoformat()
        if not note.startswith(("-", "#", "*")):
            note = f"- **{now.strftime('%H:%M')}**: {note}"
    full = _safe_path(file)
    if not full:
        return "That is not a place in the memory vault."
    os.makedirs(os.path.dirname(full), exist_ok=True)
    existing = os.path.getsize(full) if os.path.exists(full) else 0
    with open(full, "a", encoding="utf-8") as fh:
        fh.write(("\n" if existing else "") + note + "\n")
    return f"Written to memory/{os.path.relpath(full, _memory_root())}."


def _post(path, payload):
    port = int(bus.config().get("hands_port", 7318))
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def open_page(url):
    """Put a web page on his screen, through the checked endpoint."""
    try:
        d = _post("/open", {"url": url})
    except Exception as e:
        return f"Could not open it: {e}. The board may not be running."
    return f"Opened {d.get('opened')}." if d.get("ok") else f"Refused: {d.get('error')}"


def show_card(text, title=""):
    """Put a note on the board rather than reading it out."""
    import random
    try:
        board = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{int(bus.config().get('hands_port', 7318))}/board",
            timeout=TIMEOUT).read())
    except Exception as e:
        return f"The board is not running ({e})."
    board.setdefault("cards", []).append({
        "id": f"c{random.randint(100000, 999999)}", "kind": "note",
        "text": str(text)[:MAX_NOTE], "title": str(title)[:60],
        "x": round(random.uniform(0.18, 0.62), 3),
        "y": round(random.uniform(0.18, 0.55), 3),
        "w": 0.22, "h": 0.18, "tint": "#39d0d8"})
    try:
        _post("/board", board)
    except Exception as e:
        return f"Could not put it on the board: {e}"
    return "It is on the board."


REGISTRY = {
    "read_memory": read_memory,
    "remember": remember,
    "open_page": open_page,
    "show_card": show_card,
}

# The schema both Ollama and any OpenAI-compatible server understand.
SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_memory",
        "description": "Look something up in your long-term memory before answering. "
                       "Use it whenever he refers to something from before.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string",
                      "description": "What to look for. Empty returns everything."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "remember",
        "description": "Write something durable to your long-term memory. "
                       "Facts and preferences worth keeping, not passing chatter.",
        "parameters": {"type": "object", "properties": {
            "note": {"type": "string", "description": "The note to keep."},
            "file": {"type": "string",
                     "description": "Vault page, e.g. 'profile' or 'projects/lugalay'. "
                                    "Defaults to today's daily page."}},
            "required": ["note"]}}},
    {"type": "function", "function": {
        "name": "open_page",
        "description": "Open a web page on his screen. http and https only.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "The address to open."}},
            "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "show_card",
        "description": "Put text on the board for him to look at, instead of "
                       "reading a long list out loud.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "What the card says."},
            "title": {"type": "string", "description": "Short label."}},
            "required": ["text"]}}},
]


def run(name, args):
    """Execute one tool call and return what to hand back to the model."""
    fn = REGISTRY.get(name)
    if not fn:
        return f"There is no tool called {name!r}."
    if not isinstance(args, dict):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            return "Those arguments were not valid JSON."
    allowed = fn.__code__.co_varnames[:fn.__code__.co_argcount]
    args = {k: v for k, v in args.items() if k in allowed}
    try:
        return str(fn(**args))
    except TypeError as e:
        return f"Wrong arguments for {name}: {e}"
    except Exception as e:
        return f"{name} failed: {type(e).__name__}: {e}"
