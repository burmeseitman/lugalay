#!/usr/bin/env python3
"""Lugalay's voice: talk, and get an answer out loud.

Hands-free by default — it calibrates the room, waits for speech, and replies
when you stop. Set mic.mode to "ptt" in config.json to hold a key instead.

    mic  ──▶ faster-whisper ──▶ claude -p ──▶ Kokoro ──▶ speakers
                    │                │            │
                    └──── agent/bus/state.json ───┘   (the face reads this)

    ./run.sh                 normal voice session
    ./run.sh --text "hi"     skip the mic, test brain + speech
    ./run.sh --say "hi"      skip the brain, test speech only
    ./run.sh --mock-brain    echo instead of calling claude (offline testing)
    ./run.sh --check         verify every dependency and exit
"""
import argparse, collections, ctypes, ctypes.util, json, os, queue, re, signal, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT)
import bus  # noqa: E402

try:
    from eyes import look  # noqa: E402
except Exception:                      # no opencv, or a build without eyes
    look = None

try:
    sys.path.insert(0, os.path.join(AGENT, "voice"))
    import tools as local_tools  # noqa: E402
except Exception:                      # a build without them still talks
    local_tools = None

# bus decides where things live: alongside the code in a checkout, in the
# user's own directory when this is running from a packaged app.
HOME = bus.HOME
CFG = bus.config()
CONFIG_PATH = bus.CONFIG
MODELS = bus.MODELS

C = {"dim": "\033[2m", "cy": "\033[36m", "gr": "\033[32m", "am": "\033[33m",
     "rd": "\033[31m", "b": "\033[1m", "x": "\033[0m"}


def log(tag, msg, colour="dim"):
    print(f"{C[colour]}{tag:>9}{C['x']}  {msg}", flush=True)


# ─────────────────────────────── the brain ───────────────────────────────
class Brain:
    """Claude Code, headless, rooted in the agent's home so it inherits
    CLAUDE.md, the memory vault, and every tool the person already has."""

    LANG = {
        "my": ("Reply in natural, warm spoken Burmese (မြန်မာဘာသာ). "
               "Speak like a friendly, intelligent human sitting in the room: "
               "use everyday conversational Burmese (e.g. ပါတယ်၊ ဟုတ်ကဲ့ပါ၊ ရပါတယ်၊ နော်) "
               "rather than stiff formal written register (avoid ဖြစ်ပါသည်၊ ဆောင်ရွက်ပါမည်). "
               "Keep sentences relatively short (2-3 concise sentences) and use natural "
               "Burmese punctuation (၊ and ။) so speech rhythm sounds lively and human. "
               "Write English words, technical terms and acronyms in Burmese script, spelled "
               "the way they are pronounced (ဘက်ထရီ, စကရင်, အေအိုင်) — the whole reply is read "
               "by one Burmese voice, which mispronounces Latin letters."),
        "en": "Reply in English.",
    }

    def __init__(self, cfg, mock=False, lang="my"):
        self.cfg = cfg
        self.mock = mock
        self.lang = lang
        self.session_id = None
        self.history = []          # only used by the local model

    # Where `claude` actually gets installed. A GUI app launched from Finder
    # inherits almost no PATH — not the shell's, just /usr/bin:/bin and friends —
    # so the packaged build could not find the brain that a terminal run finds
    # instantly, and silently dropped to the local model instead.
    BRAIN_PATHS = ("~/.local/bin", "~/.npm-global/bin", "~/.bun/bin",
                   "~/.volta/bin", "~/n/bin", "/opt/homebrew/bin",
                   "/usr/local/bin", "~/AppData/Roaming/npm")

    @staticmethod
    def _env():
        """A spawned claude must not think it is a nested agent run."""
        env = os.environ.copy()
        for k in ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION",
                  "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDECODE"):
            env.pop(k, None)

        sep = os.pathsep
        have = env.get("PATH", "").split(sep)
        extra = [d for d in (os.path.expanduser(p) for p in Brain.BRAIN_PATHS)
                 if os.path.isdir(d) and d not in have]
        if extra:
            env["PATH"] = sep.join(have + extra)
        return env

    # ── local fallback: any local model server ─────────────────────────
    # Probed in order. Ollama has its own API; everything else speaks
    # OpenAI-compatible /v1/chat/completions.
    LOCAL_BACKENDS = [
        {"name": "ollama",   "url": "http://127.0.0.1:11434", "api": "ollama",
         "probe": "/api/tags"},
        {"name": "lmstudio", "url": "http://127.0.0.1:1234",  "api": "openai",
         "probe": "/v1/models"},
        {"name": "jan",      "url": "http://127.0.0.1:1337",  "api": "openai",
         "probe": "/v1/models"},
        {"name": "localai",  "url": "http://127.0.0.1:8080",  "api": "openai",
         "probe": "/v1/models"},
        {"name": "llamacpp", "url": "http://127.0.0.1:8081",  "api": "openai",
         "probe": "/v1/models"},
    ]

    @staticmethod
    def spoken_style(lang):
        """How to speak this language, from a file so it can be tuned live.

        The prompt is the one knob that decides whether Burmese comes out
        sounding like a person or like a textbook, and it needs trying and
        retrying against a real voice. Keeping it in a file means a change
        lands on the very next sentence instead of at the next rebuild.

        A copy under the writable root beats the one that ships, so a packaged
        install can still be tuned.
        """
        name = {"my": "spoken_burmese.md", "en": "spoken_english.md"}.get(lang)
        if not name:
            return None
        override = bus.config().get("language", {}).get(f"{lang}_prompt_file")
        for path in ([override] if override else []) + [
                os.path.join(bus.ROOT, "voice", "prompts", name),
                bus.resource("voice", "prompts", name)]:
            try:
                with open(os.path.expanduser(path), encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                continue
            # everything above the first --- is a note to whoever edits the
            # file; the model should never see it
            if "\n---\n" in body:
                body = body.split("\n---\n", 1)[1]
            body = body.strip()
            if body:
                return body
        return None

    @staticmethod
    def now_note():
        """The clock. Claude is told today's date and nothing else, so asked the
        time it either guessed or said it could not know — and a personal
        assistant that cannot tell you the time is a strange thing to own."""
        t = time.localtime()
        tz = time.strftime("%Z", t) or ""
        off = time.strftime("%z", t)
        off = f"UTC{off[:3]}:{off[3:]}" if off else ""
        return ("Right now it is " + time.strftime("%A %d %B %Y, %H:%M", t)
                + f" local time ({tz} {off})".rstrip() + ". "
                "Use this when the time or the date matters — do not say you "
                "have no way of knowing it.")

    @classmethod
    def style(cls, lang):
        """The speaking instructions for `lang`, file first, built-in second."""
        return cls.spoken_style(lang) or cls.LANG.get(lang, cls.LANG["my"])

    def _local_system(self, lang):
        """A local model has no tools, so who Lugalay is has to be handed to
        it directly instead of being read off disk."""
        parts = [self.style(lang or self.lang), self.now_note()]
        cfg = bus.config()
        parts.append(f"You are {cfg.get('name', 'the assistant')}, "
                     f"{cfg.get('user', 'the user')}'s personal assistant. Warm, "
                     "friendly, and direct. This is a REAL-TIME SPOKEN conversation: "
                     "answer in two or three short sentences of natural conversational "
                     "prose. Never output markdown formatting, lists, bullet points, "
                     "code blocks, or URLs.")
        if local_tools:
            parts.append(
                "You have tools. Use read_memory before answering anything that "
                "refers to an earlier conversation, and remember when he tells you "
                "something durable — a preference, a decision, a fact about his "
                "work. open_page puts a web page on his screen; show_card puts "
                "text on his board instead of reading a long list aloud. Call a "
                "tool when it is the right thing to do and then answer normally; "
                "never describe the call out loud.")
        try:
            with open(os.path.join(HOME, "memory", "profile.md"),
                      encoding="utf-8") as f:
                parts.append("What you know about them:\n" + f.read()[:1600])
        except OSError:
            pass
        return "\n\n".join(parts)

    @staticmethod
    def _pick_model(models, wanted):
        """Choose a model that is actually installed.

        The configured name used to be taken on trust, so deleting a model left
        the fallback calling something Ollama no longer had — it answered
        "model not found" and the local brain was silently dead, at exactly the
        moment it was needed. Prefer what is asked for, settle for what exists.
        """
        names = [m.get("name") for m in models if m.get("name")]
        if not names:
            return None
        if wanted in names:
            return wanted
        # a cloud-hosted entry is no use as an offline fallback, and the
        # smallest of the rest is the one most likely to fit in memory
        local = [m for m in models if not str(m.get("name","")).endswith(":cloud")]
        pool = local or models
        pick = min(pool, key=lambda m: m.get("size", 0)).get("name")
        if wanted:
            log("brain", f"{C['am']}{wanted} is not installed; "
                         f"using {pick} instead{C['x']}", "am")
        return pick

    def _discover_local(self):
        """Find the first local model server that is running.

        Returns (backend_dict, model_name) or (None, None).  The user's
        config can pin a specific backend via ``ollama.url``; if that is
        set and reachable it always wins.
        """
        import urllib.request

        # honour explicit config first
        o = self.cfg.get("ollama", {})
        pinned = o.get("url")
        if pinned:
            try:
                with urllib.request.urlopen(pinned + "/api/tags", timeout=2) as r:
                    models = json.loads(r.read()).get("models", [])
                    model = self._pick_model(models, o.get("model"))
                    if model:
                        return {"name": "ollama", "url": pinned,
                                "api": "ollama"}, model
            except Exception:
                pass

        # scan all known backends
        for be in self.LOCAL_BACKENDS:
            try:
                with urllib.request.urlopen(be["url"] + be["probe"],
                                            timeout=1.5) as r:
                    body = json.loads(r.read())
                    if be["api"] == "ollama":
                        names = [m["name"] for m in body.get("models", [])]
                        model = self._pick_model(body.get("models", []),
                                                 o.get("model"))
                        if not model:
                            continue
                    else:
                        names = [m["id"] for m in body.get("data", [])]
                        model = names[0] if names else "default"
                    log("brain", f"{C['gr']}found {be['name']} at {be['url']} "
                                 f"({', '.join(names[:3])}){C['x']}", "gr")
                    return be, model
            except Exception:
                continue
        return None, None

    MAX_TOOL_ROUNDS = 4

    def _split_first_sentence(self, answer):
        """Yield (opening sentence, True) and (rest, False), so the mouth can
        start speaking while the tail is still being rendered by the voice."""
        m = SENT_END.search(answer)
        if m and m.end() >= 12 and m.end() < len(answer):
            yield answer[:m.end()].strip(), True
            yield answer[m.end():].strip(), False
        else:
            yield answer, True

    def _remote_tool_round(self, url, model, key, text, lang):
        """Same idea as _tool_round but for an OpenAI-compatible endpoint."""
        import urllib.request
        self.history.append({"role": "user", "content": text})
        messages = [{"role": "system", "content": self._local_system(lang)}] \
                   + self.history[-8:]
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {key}"}
        endpoint = url.rstrip("/") + "/v1/chat/completions"
        for _ in range(self.MAX_TOOL_ROUNDS):
            payload = {"model": model, "messages": messages, "stream": False,
                       "tools": local_tools.SCHEMAS, "temperature": 0.7,
                       "max_tokens": int(self.cfg.get("ollama", {}).get("max_tokens", 220))}
            req = urllib.request.Request(
                endpoint, data=json.dumps(payload).encode(),
                headers=headers, method="POST")
            with urllib.request.urlopen(
                    req, timeout=self.cfg.get("timeout_seconds", 180)) as r:
                d = json.loads(r.read())
            msg = ((d.get("choices") or [{}])[0].get("message")) or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                answer = (msg.get("content") or "").strip()
                if answer:
                    self.history.append({"role": "assistant", "content": answer})
                return answer
            messages.append(msg)
            for c in calls:
                fn = (c.get("function") or {})
                name = fn.get("name", "")
                out = local_tools.run(name, fn.get("arguments"))
                log("brain", f"{C['dim']}tool {name} -> {out[:60]}{C['x']}", "dim")
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""),
                                 "name": name, "content": out})
        return None

    def _tool_round(self, url, model, o, messages):
        """Let a local model use tools, then hand back what it finally said.

        Claude comes with its own tools; a local model comes with none, so the
        offline brain could only talk — it could not read what it had been told
        last week or write down what it had just learned. Ollama and every
        OpenAI-compatible server take the same `tools` schema and answer with
        `tool_calls`, so one loop serves both.

        Runs unstreamed: a tool round has nothing to say out loud, and the
        answer is split into sentences downstream anyway.
        """
        import urllib.request
        if not local_tools:
            return None
        for _ in range(self.MAX_TOOL_ROUNDS):
            payload = {"model": model, "messages": messages, "stream": False,
                       "think": bool(o.get("think", False)),
                       "keep_alive": o.get("keep_alive", "30m"),
                       "tools": local_tools.SCHEMAS,
                       "options": {"temperature": 0.7,
                                   "num_predict": int(o.get("max_tokens", 220))}}
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(
                    req, timeout=self.cfg.get("timeout_seconds", 180)) as r:
                d = json.loads(r.read())
            msg = d.get("message") or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                return (msg.get("content") or "").strip()
            messages.append(msg)
            for c in calls:
                fn = (c.get("function") or {})
                name = fn.get("name", "")
                out = local_tools.run(name, fn.get("arguments"))
                log("brain", f"{C['dim']}tool {name} -> {out[:60]}{C['x']}", "dim")
                messages.append({"role": "tool", "name": name, "content": out})
        # it kept reaching for tools and never answered
        return None

    def _ollama_stream(self, text, lang=None):
        """Yield (piece, is_first) from a local Ollama model."""
        import urllib.request
        o = self.cfg.get("ollama", {})
        url = o.get("url", "http://127.0.0.1:11434") + "/api/chat"
        self.history.append({"role": "user", "content": text})
        payload = {
            "model": o.get("model", "qwen3:8b"),
            "messages": [{"role": "system", "content": self._local_system(lang)}]
                        + self.history[-8:],
            "stream": True,
            "think": bool(o.get("think", False)),
            # Ollama drops the model out of memory five minutes after the last
            # request. In a spoken conversation that is a normal gap between
            # questions, and reloading 5GB off disk cost a measured 4-9 seconds
            # before a single token appeared — the whole reason offline mode
            # felt slow. Hold it resident instead.
            "keep_alive": o.get("keep_alive", "30m"),
            "options": {"temperature": 0.7,
                        "num_predict": int(o.get("max_tokens", 220))},
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")

        # Give it its tools first. If it wants none, this is one extra call and
        # the answer comes back whole; if it wants some, this is the only way
        # it ever gets to use them.
        answer = None
        try:
            answer = self._tool_round(url, payload["model"], o,
                                      list(payload["messages"]))
        except Exception as e:
            log("brain", f"{C['am']}tools unavailable ({e}); "
                         f"answering without them{C['x']}", "am")
        if answer:
            self.history.append({"role": "assistant", "content": answer})
            m = SENT_END.search(answer)
            if m and m.end() >= 12 and m.end() < len(answer):
                yield answer[:m.end()].strip(), True
                yield answer[m.end():].strip(), False
            else:
                yield answer, True
            return

        buf, sent_first, full = "", False, ""
        with urllib.request.urlopen(req, timeout=self.cfg.get("timeout_seconds", 180)) as r:
            for raw in r:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                piece = (d.get("message") or {}).get("content", "")
                if piece:
                    buf += piece
                    full += piece
                    if not sent_first:
                        m = SENT_END.search(buf)
                        if m and m.end() >= 12:
                            head, buf = buf[:m.end()].strip(), buf[m.end():]
                            sent_first = True
                            yield head, True
                if d.get("done"):
                    break
        rest = buf.strip()
        if rest:
            yield rest, not sent_first
        elif not sent_first:
            yield "I do not have anything to say to that.", True
        self.history.append({"role": "assistant", "content": full.strip()})

    # A handful of the common providers keyed by short name, so a config
    # only has to name them rather than remember their URLs.
    REMOTE_PRESETS = {
        "openai":     {"url": "https://api.openai.com",           "model": "gpt-4o-mini"},
        "groq":       {"url": "https://api.groq.com/openai",      "model": "llama-3.3-70b-versatile"},
        "together":   {"url": "https://api.together.xyz",         "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo"},
        "openrouter": {"url": "https://openrouter.ai/api",        "model": "openai/gpt-4o-mini"},
        "deepseek":   {"url": "https://api.deepseek.com",         "model": "deepseek-chat"},
    }

    def _remote_stream(self, text, lang=None):
        """Route to a hosted OpenAI-compatible service using the same code
        path as the local one. Named for clarity in the log."""
        engine = self.cfg.get("engine", "openai")
        r = dict(self.REMOTE_PRESETS.get(engine, {}))
        r.update({k: v for k, v in (self.cfg.get("remote") or {}).items() if v})
        url   = r.get("url")
        model = r.get("model")
        key   = r.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        if not url or not model:
            yield ("I have no remote model configured — set brain.remote.url "
                   "and brain.remote.model in the config."), True
            return
        if not key:
            yield ("I have no key for the remote model. Put it in "
                   "brain.remote.api_key or the OPENAI_API_KEY environment."), True
            return
        try:
            if local_tools:
                answer = self._remote_tool_round(url, model, key, text, lang)
                if answer:
                    for piece in self._split_first_sentence(answer):
                        yield piece
                    return
            yield from self._openai_stream(text, lang, url=url, model=model,
                                           api_key=key)
        except Exception as e:
            log("brain", f"{C['am']}remote failed ({e}); "
                         f"falling back to local model{C['x']}", "am")
            if self.local_available():
                yield from self._local_stream(text, lang)
            else:
                yield f"The remote model refused: {e}", True

    def _openai_stream(self, text, lang=None, url="http://127.0.0.1:1234",
                       model="default", api_key=None):
        """Yield (piece, is_first) from anything speaking OpenAI's chat API.

        The same wire format serves LM Studio, Jan, LocalAI, llama.cpp on one
        end and OpenAI, Groq, Together, DeepSeek, OpenRouter on the other. The
        only thing a hosted service adds is an Authorization header; supply an
        api_key and it goes out, leave it None and the request is anonymous the
        way a local server expects.
        """
        import urllib.request
        endpoint = url.rstrip("/") + "/v1/chat/completions"
        self.history.append({"role": "user", "content": text})
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": self._local_system(lang)}]
                        + self.history[-8:],
            "stream": True,
            "temperature": 0.7,
            "max_tokens": int(self.cfg.get("ollama", {}).get("max_tokens", 220)),
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            endpoint, data=json.dumps(payload).encode(),
            headers=headers, method="POST")

        buf, sent_first, full = "", False, ""
        with urllib.request.urlopen(req, timeout=self.cfg.get("timeout_seconds", 180)) as r:
            for raw in r:
                raw = raw.strip()
                if not raw or raw == b"data: [DONE]":
                    continue
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                delta = (d.get("choices") or [{}])[0].get("delta", {})
                piece = delta.get("content", "")
                if piece:
                    buf += piece
                    full += piece
                    if not sent_first:
                        m = SENT_END.search(buf)
                        if m and m.end() >= 12:
                            head, buf = buf[:m.end()].strip(), buf[m.end():]
                            sent_first = True
                            yield head, True
        rest = buf.strip()
        if rest:
            yield rest, not sent_first
        elif not sent_first:
            yield "I do not have anything to say to that.", True
        self.history.append({"role": "assistant", "content": full.strip()})

    def _local_stream(self, text, lang=None):
        """Try any available local backend. Returns a generator of (piece, is_first)."""
        be, model = self._discover_local()
        if be is None:
            yield "No local model server is running. Start Ollama or LM Studio.", True
            return
        log("brain", f"{C['am']}using {be['name']} model {model}{C['x']}", "am")
        if be["api"] == "ollama":
            # patch config so _ollama_stream picks the right url/model
            o = self.cfg.setdefault("ollama", {})
            o.setdefault("url", be["url"])
            o.setdefault("model", model)
            yield from self._ollama_stream(text, lang)
        else:
            yield from self._openai_stream(text, lang, url=be["url"], model=model)

    @staticmethod
    def ollama_up(url="http://127.0.0.1:11434"):
        import urllib.request
        try:
            with urllib.request.urlopen(url + "/api/tags", timeout=2):
                return True
        except Exception:
            return False

    def warm_local(self):
        """Load the local model into memory now, in the background.

        Ollama loads a model on first use, not on start, so the first question
        of a session paid the whole 4-9s read off disk before anything came
        back. Nothing depends on this finishing — if it fails, the first reply
        is simply as slow as it used to be.
        """
        o = self.cfg.get("ollama", {})
        if self.cfg.get("engine") not in ("ollama", "lmstudio", "local"):
            return
        def go():
            import urllib.request
            try:
                # Send the real system prompt, not an empty request. Loading the
                # weights is only half the cold cost — the other half is reading
                # the ~1500-token system prompt, and doing it here leaves it in
                # the KV cache so his first question reuses it instead of paying
                # for it again.
                body = json.dumps({
                    "model": o.get("model", "qwen3:8b"),
                    "messages": [{"role": "system",
                                  "content": self._local_system(self.lang)},
                                 {"role": "user", "content": "hi"}],
                    "stream": False,
                    "think": bool(o.get("think", False)),
                    "keep_alive": o.get("keep_alive", "30m"),
                    "options": {"num_predict": 1},
                }).encode()
                req = urllib.request.Request(
                    o.get("url", "http://127.0.0.1:11434") + "/api/chat",
                    data=body, headers={"Content-Type": "application/json"},
                    method="POST")
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=180):
                    pass
                log("brain", f"{C['dim']}local model warm "
                             f"({time.time()-t0:.1f}s){C['x']}", "dim")
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()

    def local_available(self):
        """Is any local model server reachable?"""
        be, _ = self._discover_local()
        return be is not None



    def stream(self, text, lang=None):
        """Yield the reply in pieces as it is generated.

        Waiting for the whole reply before synthesising anything meant the
        brain's generation time and the speech time were strictly additive.
        Measured: first token lands at ~2.0s but the full reply only at ~4.5s,
        so speaking the opening sentence early hides most of that.

        Yields (piece, is_first). The first piece is the opening sentence, sent
        the moment it is complete; the rest arrives as one block so the tail of
        the answer still sounds continuous.
        """
        if self.mock:
            time.sleep(0.4)
            yield f"You said: {text}", True
            return

        engine = self.cfg.get("engine", "claude")
        if engine in ("openai", "remote", "groq", "together", "openrouter",
                      "deepseek"):
            yield from self._remote_stream(text, lang)
            return
        if engine in ("ollama", "lmstudio", "local"):
            yield from self._local_stream(text, lang)
            return

        cmd = self._cmd(text, lang, streaming=True)
        try:
            # text=True alone decodes with the locale encoding, which on
            # Windows is cp1252 and cannot represent a word of Burmese — the
            # reply would arrive as a UnicodeDecodeError instead of speech.
            proc = subprocess.Popen(cmd, cwd=HOME, env=self._env(),
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True,
                                    encoding="utf-8", errors="replace")
        except FileNotFoundError:
            if (self.cfg.get("engine") in ("auto", "claude", "local")
                    and self.local_available()):
                log("brain", f"{C['am']}claude not installed; "
                             f"falling back to local model{C['x']}", "am")
                yield from self._local_stream(text, lang)
                return
            yield "I cannot find the claude command, so I have no brain right now.", True
            return

        buf, sent_first, err = "", False, None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            kind = d.get("type")
            if kind == "stream_event":
                ev = d.get("event", {})
                if ev.get("type") == "content_block_delta":
                    buf += ev.get("delta", {}).get("text", "") or ""
                    if not sent_first:
                        m = SENT_END.search(buf)
                        # only break early on a sentence long enough to be worth
                        # speaking; "ok." alone would just add a seam
                        if m and m.end() >= 12:
                            head, buf = buf[:m.end()].strip(), buf[m.end():]
                            sent_first = True
                            yield head, True
            elif kind == "result":
                if d.get("session_id"):
                    self.session_id = d["session_id"]
                if d.get("is_error"):
                    err = (d.get("result") or "").strip()
        proc.wait()

        if err:
            if (self.cfg.get("engine") in ("auto", "claude", "local") and not sent_first
                    and self.local_available()):
                log("brain", f"{C['am']}claude failed ({err}); "
                             f"falling back to local model{C['x']}", "am")
                yield from self._local_stream(text, lang)
                return
            yield f"My brain refused that one. It said: {err}", not sent_first
            return
        rest = buf.strip()
        if rest:
            yield rest, not sent_first
        elif not sent_first:
            yield "I do not have anything to say to that.", True

    def ask(self, text, lang=None):
        if self.mock:
            time.sleep(0.4)
            return f"You said: {text}"

        engine = self.cfg.get("engine", "claude")
        if engine in ("openai", "remote", "groq", "together", "openrouter",
                      "deepseek"):
            parts = list(self._remote_stream(text, lang))
            return " ".join(p for p, _ in parts).strip() or \
                   "I do not have anything to say to that."
        if engine in ("ollama", "lmstudio", "local"):
            parts = list(self._local_stream(text, lang))
            return " ".join(p for p, _ in parts).strip() or \
                   "I do not have anything to say to that."

        cmd = self._cmd(text, lang)
        try:
            p = subprocess.run(cmd, cwd=HOME, env=self._env(), capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=self.cfg.get("timeout_seconds", 180))
        except subprocess.TimeoutExpired:
            return "Sorry, that took too long and I gave up on it."
        except FileNotFoundError:
            if (self.cfg.get("engine") in ("auto", "claude", "local")
                    and self.local_available()):
                log("brain", f"{C['am']}claude not installed; "
                             f"falling back to local model{C['x']}", "am")
                parts = list(self._local_stream(text, lang))
                return " ".join(p for p, _ in parts).strip() or \
                       "I do not have anything to say to that."
            return "I cannot find the claude command, so I have no brain right now."
        return self._parse(p.stdout, p.stderr)

    def _cmd(self, text, lang=None, streaming=False):
        cmd = [self.cfg.get("cmd", "claude"), "-p", text,
               "--output-format", "stream-json" if streaming else "json",
               # headless runs ignore project settings unless asked; without
               # this the permission allowlist in .claude/settings.json is
               # invisible and Lugalay cannot even write its own memory
               "--setting-sources", "user,project,local",
               "--append-system-prompt",
               # CLAUDE.md carries the same rules, but this flag lands later and
               # wins — leaving language out of it made the reply language drift
               # to whatever the question was asked in.
               self.style(lang or self.lang) + "\n\n" + self.now_note() + "\n\n"
               "This is a SPOKEN conversation. Answer in two or three sentences of "
               "plain prose. No markdown, no lists, no code blocks, no URLs — every "
               "one of those sounds like noise when read aloud. If the answer truly "
               "needs code or a long list, write it to a file and say where you put it."]
        if streaming:
            cmd += ["--include-partial-messages", "--verbose"]

        # Latency work, measured: every spawn re-reads the whole context, and
        # loading MCP servers plus the skill catalogue on each turn cost about
        # 1.5s of the wait before Lugalay says anything. None of it is used in
        # a spoken exchange.
        if self.cfg.get("fast", True):
            cmd += ["--strict-mcp-config", "--disable-slash-commands"]
            effort = self.cfg.get("effort")
            if effort:
                cmd += ["--effort", effort]

        if self.cfg.get("permission_mode") == "auto":
            cmd += ["--permission-mode", "bypassPermissions"]
        if self.session_id and self.cfg.get("continue_session", True):
            cmd += ["--resume", self.session_id]

        return cmd

    def _parse(self, stdout, stderr=""):
        try:
            d = json.loads(stdout)
        except ValueError:
            err = (stderr or stdout or "no output").strip().splitlines()
            log("brain", f"{C['rd']}unparseable output: {err[:1]}{C['x']}", "rd")
            return "Something went wrong reaching my brain."
        if d.get("session_id"):
            self.session_id = d["session_id"]
        result = (d.get("result") or "").strip()
        if d.get("is_error"):
            log("brain", f"{C['rd']}error: {result}{C['x']}", "rd")
            return f"My brain refused that one. It said: {result}"
        return result or "I do not have anything to say to that."


# ──────────────────────────────── the ears ───────────────────────────────
class Ears:
    def __init__(self, cfg):
        import sounddevice as sd
        self.sd = sd
        self.rate = int(cfg["mic"].get("samplerate", 16000))
        self.max_s = int(cfg["mic"].get("max_seconds", 30))
        self.device = self._resolve(cfg["mic"].get("device"))
        self.frames, self.stream, self.level = [], None, 0.0

    @staticmethod
    def _resolve(want):
        """None means the system default. An int is a device index. A string
        matches on name, so 'MacBook' survives the device list reordering."""
        if want is None:
            return None
        import sounddevice as sd
        if isinstance(want, int):
            return want
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and want.lower() in d["name"].lower():
                return i
        log("mic", f"{C['am']}no input device matching {want!r}; "
                   f"using the system default{C['x']}", "am")
        return None

    def _cb(self, indata, frames, t, status):
        import numpy as np
        self.frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(np.square(indata))))
        self.level = min(1.0, rms * 9)

    def start(self):
        self.frames, self.level = [], 0.0
        self.stream = self.sd.InputStream(samplerate=self.rate, channels=1,
                                          dtype="float32", callback=self._cb,
                                          blocksize=1024, device=self.device)
        self.stream.start()

    def stop(self):
        import numpy as np
        if not self.stream:
            return np.zeros(0, dtype="float32")
        self.stream.stop(); self.stream.close(); self.stream = None
        if not self.frames:
            return np.zeros(0, dtype="float32")
        audio = np.concatenate(self.frames, axis=0).flatten()
        return audio[: self.rate * self.max_s]


class OpenMic:
    """Hands-free listening. No key: talk when you feel like it.

    An adaptive energy gate decides when speech starts and stops, and Silero
    VAD (already bundled with faster-whisper) vets the captured utterance so
    a door slam or a cough never reaches the brain.

    The microphone is muted while Lugalay is talking. Without that it hears
    its own voice through the speakers and answers itself forever.
    """

    def __init__(self, cfg, events):
        import sounddevice as sd
        self.sd = sd
        m = cfg["mic"]
        self.rate = int(m.get("samplerate", 16000))
        self.max_s = int(m.get("max_seconds", 30))
        self.device = Ears._resolve(m.get("device"))
        self.start_ratio = float(m.get("open_sensitivity", 4.0))
        self.hang_s = float(m.get("open_silence_seconds", 0.9))
        self.min_s = float(m.get("open_min_seconds", 0.4))
        self.events = events

        self.block = 512                       # 32 ms at 16 kHz
        self.pre_roll = int(0.4 * self.rate / self.block)
        self.noise = 0.004                     # updated continuously
        self.calibrating = int(1.0 * self.rate / self.block)
        self.cal = []

        self.ring = collections.deque(maxlen=self.pre_roll)
        self.buf = []
        self.speaking = False                  # are WE hearing speech?
        self.quiet = 0
        self.loud = 0
        self.muted = True                      # until the greeting finishes
        self.level = 0.0
        self.stream = None
        self._vad = None

    # ── the gate ──────────────────────────────────────────────────────
    def _cb(self, indata, frames, t, status):
        import numpy as np
        block = indata.copy().flatten()
        rms = float(np.sqrt(np.mean(np.square(block))))
        self.level = min(1.0, rms * 9)

        if self.muted:
            self.ring.clear()
            return

        if self.calibrating > 0:               # learn the room first
            self.cal.append(rms)
            self.calibrating -= 1
            if self.calibrating == 0:
                self.cal.sort()
                self.noise = max(0.0008, self.cal[len(self.cal) // 2])
                log("mic", f"{C['dim']}room noise {self.noise:.4f} — "
                           f"listening, just talk{C['x']}")
            return

        on = max(self.noise * self.start_ratio, 0.006)
        off = max(self.noise * (self.start_ratio * 0.5), 0.003)

        if not self.speaking:
            self.ring.append(block)
            if rms > on:
                self.loud += 1
                if self.loud >= 3:             # ~100 ms, not a click
                    self.speaking = True
                    self.quiet = 0
                    self.buf = list(self.ring)  # keep the first syllable
                    self.ring.clear()
                    bus.write("listening", "", self.level)
            else:
                self.loud = 0
                # drift with the room while it is quiet
                self.noise = self.noise * 0.995 + rms * 0.005
            return

        self.buf.append(block)
        if rms < off:
            self.quiet += 1
        else:
            self.quiet = 0

        held = len(self.buf) * self.block / self.rate
        done = self.quiet * self.block / self.rate >= self.hang_s
        if done or held >= self.max_s:
            self.speaking = False
            self.loud = 0
            audio = np.concatenate(self.buf).astype("float32")
            self.buf = []
            if held >= self.min_s:
                self.muted = True              # stop listening until answered
                self.events.put(("utterance", audio))
            else:
                bus.write("idle")

    # ── Silero vetting, so noise never reaches the brain ──────────────
    def is_speech(self, audio):
        import numpy as np
        try:
            if self._vad is None:
                from faster_whisper.vad import get_vad_model
                self._vad = get_vad_model()
            n = (len(audio) // 512) * 512
            if n < 512:
                return False
            probs = self._vad(audio[:n].astype("float32"))
            return float(np.max(probs)) > 0.5
        except Exception:
            return True                        # never block on a broken vet

    def start(self):
        self.stream = self.sd.InputStream(
            samplerate=self.rate, channels=1, dtype="float32",
            callback=self._cb, blocksize=self.block, device=self.device)
        self.stream.start()

    def stop(self):
        if self.stream:
            self.stream.stop(); self.stream.close(); self.stream = None

    def listen(self):
        """Reopen the gate after Lugalay finishes talking.
        Includes an acoustic cooldown so the microphone does not catch
        the tail of the speaker's own echo in hands-free mode."""
        time.sleep(0.35)
        self.buf = []
        self.ring.clear()
        self.speaking = False
        self.loud = self.quiet = 0
        self.muted = False


class Transcriber:
    """Speech to text, in Burmese or English, decided per utterance.

    Stock Whisper cannot transcribe Burmese at any size, and the Burmese
    fine-tune cannot transcribe English — it hears "can you hear me" as
    Burmese gibberish. So there are two models and a small third one whose
    only job is to say which language just arrived.

    `whisper base` was chosen for that job because `tiny` mistakes Burmese
    for Thai; base gets it right at p=0.84 in under two tenths of a second.
    """

    # Whisper's language id NEVER returns "my" for real Burmese speech.
    # Measured on a real Burmese speaker: it answered zh p=0.87, and on other
    # samples th and cy. English, by contrast, it identifies confidently
    # (p=0.82-0.99). So the only trustworthy question is "was that English?"
    # — - everything else is Burmese, which is also the default language here.
    EN_MIN_PROB = 0.5

    def __init__(self, cfg):
        from faster_whisper import WhisperModel
        s = cfg["stt"]
        self.cfg = s
        self.bilingual = s.get("mode", "single") == "bilingual"
        self.compute = s.get("compute_type", "int8")
        self.threads = os.cpu_count() or 4
        self._WM = WhisperModel
        self.cache = {}

        if self.bilingual:
            names = s.get("models", {})
            self.name_my = names.get("my", "whisper-my-turbo")
            self.name_en = names.get("en", "small.en")
            self.en_min = float(s.get("english_min_prob", self.EN_MIN_PROB))
            # The Burmese model is a local conversion, not something pip or
            # faster-whisper can fetch, so a fresh install may not have it.
            # English still works; say so once and carry on.
            if not os.path.isdir(os.path.join(MODELS, self.name_my)):
                log("stt", f"{C['am']}no Burmese model at models/{self.name_my} — "
                           f"English only.{C['x']}", "am")
                log("", "add it with:  python3 agent/fetch_models.py --burmese")
                self.bilingual = False
                self.lang = "en"
                self.single = self._load(self.name_en)
                return
            log("stt", f"loading {self.name_en} + {self.name_my} + language id …")
            self.lid = self._load(s.get("lid_model", "base"))
            self._load(self.name_en)
            self._load(self.name_my)
        else:
            log("stt", f"loading {s['model']} …")
            self.lang = s.get("language") or None
            self.single = self._load(s["model"])

    def _load(self, name):
        if name in self.cache:
            return self.cache[name]
        local = os.path.join(MODELS, name)
        path = local if os.path.isdir(local) else name
        m = self._WM(path, device="cpu", compute_type=self.compute,
                     download_root=os.path.join(MODELS, "whisper"),
                     cpu_threads=self.threads)
        self.cache[name] = m
        return m

    def _google_transcribe(self, audio, lang="my-MM"):
        """Transcribe audio using Google's Speech-to-Text API (95%+ accuracy for Burmese).
        Uses native in-memory FLAC encoding via soundfile with zero external binaries."""
        try:
            import io, json, urllib.request, urllib.parse
            import soundfile as sf
            import numpy as np

            # Ensure float32 audio
            if audio.dtype != np.float32:
                audio_float = audio.astype(np.float32) / 32767.0
            else:
                audio_float = audio

            flac_buf = io.BytesIO()
            sf.write(flac_buf, audio_float, 16000, format="FLAC", subtype="PCM_16")
            flac_data = flac_buf.getvalue()

            key = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
            params = urllib.parse.urlencode({
                "client": "chromium",
                "lang": lang,
                "key": key,
                "pFilter": 0
            })
            url = f"http://www.google.com/speech-api/v2/recognize?{params}"
            headers = {"Content-Type": "audio/x-flac; rate=16000", "User-Agent": "Mozilla/5.0"}

            req = urllib.request.Request(url, data=flac_data, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                for line in resp.read().decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    results = d.get("result", [])
                    if results:
                        alts = results[0].get("alternative", [])
                        if alts:
                            transcript = alts[0].get("transcript", "").strip()
                            if transcript:
                                return transcript
            return None
        except Exception as e:
            log("stt", f"{C['am']}Google STT request failed ({e}){C['x']}", "am")
            return None

    def __call__(self, audio):
        """Returns (text, language) — obeys user's configured listening language."""
        if audio.size < 4000:          # under a quarter second: a slip, not speech
            return "", None

        cfg = bus.config()
        listen_mode = cfg.get("language", {}).get("listen", "my")

        # 1. Explicit Burmese Listening Mode
        if listen_mode == "my":
            if self.cfg.get("google", True):
                g_text = self._google_transcribe(audio, "my-MM")
                if g_text:
                    log("stt", f"{C['gr']}Google Speech recognized (my-MM): {g_text}{C['x']}", "gr")
                    return g_text, "my"
            # Offline Burmese fallback
            if hasattr(self, "name_my") and os.path.isdir(os.path.join(MODELS, self.name_my)):
                model = self._load(self.name_my)
                segs, _ = model.transcribe(audio, language="my", beam_size=1, vad_filter=True)
                return " ".join(x.text for x in segs).strip(), "my"
            return "", "my"

        # 2. Explicit English Listening Mode
        if listen_mode == "en":
            if self.cfg.get("google", True):
                g_text = self._google_transcribe(audio, "en-US")
                if g_text:
                    log("stt", f"{C['gr']}Google Speech recognized (en-US): {g_text}{C['x']}", "gr")
                    return g_text, "en"
            model_name = getattr(self, "name_en", "small.en")
            model = self._load(model_name)
            segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
            return " ".join(x.text for x in segs).strip(), "en"

        # 3. Auto / Bilingual Mode
        if not self.bilingual:
            segs, _ = self.single.transcribe(
                audio, language=self.lang, beam_size=1, vad_filter=True,
                condition_on_previous_text=False)
            return " ".join(x.text for x in segs).strip(), self.lang

        # Try Google STT for Burmese first (95%+ accuracy)
        if self.cfg.get("google", True):
            g_text = self._google_transcribe(audio, "my-MM")
            if g_text and is_burmese(g_text):
                log("stt", f"{C['gr']}Google Speech recognized (my-MM): {g_text}{C['x']}", "gr")
                return g_text, "my"

        # If not recognized as Burmese, check language ID for English or fallback
        try:
            lang, prob, _ = self.lid.detect_language(audio)
        except Exception as e:
            log("stt", f"{C['am']}language id failed ({e}); assuming English{C['x']}", "am")
            lang, prob = "en", 0.0

        english = lang == "en" and prob >= self.en_min
        model_name = self.name_en if english else self.name_my
        forced = "en" if english else "my"
        if not english and not os.path.isdir(os.path.join(MODELS, self.name_my)):
            model_name = self.name_en
            forced = "en"

        model = self._load(model_name)
        log("stt", f"{C['dim']}local whisper {model_name} (forced={forced}){C['x']}")
        segs, _ = model.transcribe(audio, language=forced, beam_size=1,
                                   vad_filter=True,
                                   condition_on_previous_text=False)
        return " ".join(x.text for x in segs).strip(), forced


# ──────────────────────────────── the mouth ──────────────────────────────
# How long one piece of speech may take to come back from the network before we
# give up on it and let the OS voice say it instead. Generous — a slow line is
# still better than the system voice — but finite.
SYNTH_TIMEOUT = 20
# How many times to ask for one piece of speech before giving up on it.
SYNTH_TRIES = 3

SENT = re.compile(r"(?<=[.!?…။၊])\s+|(?<=[။၊])")
MYANMAR = re.compile(r"[\u1000-\u109F\uAA60-\uAA7F]")
SENT_END = re.compile(r"[.!?…။]")


def is_burmese(text):
    """Route by script, not by a config flag — a bilingual agent mixes
    languages inside one answer and each sentence needs its own voice."""
    return bool(MYANMAR.search(text))


_TERMS_CACHE = {"mtime": None, "path": None, "pairs": []}


def burmese_terms():
    """English → Burmese-script pairs, longest first, re-read when the file changes.

    Asking the model to transliterate turned out to be unreliable — it ignores
    the instruction about half the time and invents bad spellings the other
    half. This table is the guarantee behind that request.
    """
    for path in (os.path.join(bus.ROOT, "voice", "prompts", "burmese_terms.txt"),
                 bus.resource("voice", "prompts", "burmese_terms.txt")):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if _TERMS_CACHE["path"] == path and _TERMS_CACHE["mtime"] == mtime:
            return _TERMS_CACHE["pairs"]
        pairs = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if "=" not in line:
                        continue
                    en, my = (p.strip() for p in line.split("=", 1))
                    if en and my:
                        pairs.append((en, my))
        except OSError:
            continue
        # longest first so "machine learning" is taken before "machine"
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
        _TERMS_CACHE.update(path=path, mtime=mtime, pairs=pairs)
        return pairs
    return []


def transliterate_terms(text):
    """Swap known English words for how they are actually said in Burmese."""
    for en, my in burmese_terms():
        # \b does not fit words with hyphens in them, so bound on non-letters
        text = re.sub(rf"(?<![A-Za-z]){re.escape(en)}(?![A-Za-z])", my, text,
                      flags=re.IGNORECASE)
    return text


def format_burmese_for_speech(text):
    """Format Burmese text specifically for natural neural TTS prosody.
    Adds breathing spaces around English loanwords, inserts natural pauses,
    and ensures proper sentence-ending cadence."""
    if not text:
        return ""
    # 0. Say English words the Burmese way. Must come first: everything below
    #    keys off which script a character is in.
    text = transliterate_terms(text)
    # 1. Add breathing spaces around Latin/English words inside Burmese text
    text = re.sub(r"([a-zA-Z0-9]+)([\u1000-\u109F\uAA60-\uAA7F])", r"\1 \2", text)
    text = re.sub(r"([\u1000-\u109F\uAA60-\uAA7F])([a-zA-Z0-9]+)", r"\1 \2", text)
    # 2. Convert English periods/commas to Myanmar punctuation when preceded by Burmese
    text = re.sub(r"([\u1000-\u109F\uAA60-\uAA7F])\s*\.\s*", r"\1။ ", text)
    text = re.sub(r"([\u1000-\u109F\uAA60-\uAA7F])\s*,\s*", r"\1၊ ", text)
    # 3. Ensure sentence ends with Myanmar full stop for natural falling intonation
    text = text.strip()
    if text and ('\u1000' <= text[-1] <= '\u109F'):
        text += "။"
    # 4. Clean consecutive punctuation
    text = re.sub(r"([။၊])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_spoken_text(text):
    """Clean LLM output so it sounds like natural, human speech when spoken aloud.
    Removes markdown formatting, emojis, asterisks, bullet points, raw code, XML/think tags,
    and normalizes punctuation for natural breathing pauses."""
    if not text:
        return ""
    # Strip XML/HTML tags and reasoning artifacts (e.g. <think>...</think>)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    # Strip URLs
    text = re.sub(r"https?://\S+", "link", text)
    # Strip markdown code blocks, backticks, bold, italics, headers
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Strip list item prefixes: '1. ', '- ', '* ', '• '
    text = re.sub(r"^\s*[\d]+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    # Strip emojis and unicode symbols
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[\u2600-\u27ff]", "", text)
    # Unwrap parenthetical asides. The engine treats a bracket as a hard stop
    # and the sentence comes out limping, so keep the words and drop the
    # brackets rather than dropping the aside with them.
    text = re.sub(r"[\(\)\[\]（）【】]", " ", text)
    # Normalize punctuation and pauses
    text = re.sub(r"\.{2,}", "…", text)
    text = re.sub(r"[!]{2,}", "!", text)
    text = re.sub(r"[?]{2,}", "?", text)
    text = re.sub(r"[|/\\#@^~]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class Mouth:
    """Kokoro, sentence by sentence, so the first words land while the rest
    is still being synthesised. Falls back to macOS `say` if Kokoro cannot
    load — a voice that degrades is better than a voice that dies."""

    def __init__(self, cfg):
        self.cfg = cfg["tts"]
        self.kokoro = None
        self.stop_flag = threading.Event()
        try:
            from kokoro_onnx import Kokoro
            m = os.path.join(MODELS, "kokoro-v1.0.onnx")
            v = os.path.join(MODELS, "voices-v1.0.bin")
            if not (os.path.exists(m) and os.path.exists(v)):
                raise FileNotFoundError("kokoro model files missing")
            log("tts", "loading kokoro …")
            self.kokoro = Kokoro(m, v)
        except Exception as e:
            log("tts", f"{C['am']}kokoro unavailable ({e}); using macOS say{C['x']}", "am")

    # Kokoro is synthesised locally per sentence so the first words start
    # early. edge-tts is a single network round trip either way, and splitting
    # it puts an audible gap between every sentence — so Burmese runs go out
    # whole, however long they are.
    LIMIT_EN, LIMIT_MY = 220, 4000

    @classmethod
    def _chunks(cls, text):
        """Group sentences into speakable runs, but never merge across a
        change of script — each language has to reach its own voice."""
        out, buf = [], ""
        for s in SENT.split(text.replace("\n", " ")):
            s = s.strip()
            if not s:
                continue
            same_script = buf and (is_burmese(buf) == is_burmese(s))
            limit = cls.LIMIT_MY if is_burmese(s) else cls.LIMIT_EN
            if buf and same_script and len(buf) + len(s) < limit:
                buf = f"{buf} {s}".strip()
            else:
                buf and out.append(buf)
                buf = s
        buf and out.append(buf)
        return out or [text]

    def _speak_burmese_google(self, text, on_level=None):
        """Synthesize Burmese using Google's Free 24kHz Speech Engine (soft, natural tone)."""
        import io, urllib.request, urllib.parse
        import numpy as np, sounddevice as sd, soundfile as sf
        try:
            sentences = [s.strip() for s in text.replace("\n", " ").split("။") if s.strip()]
            if not sentences:
                sentences = [text]
            all_samples = []
            sample_rate = 24000
            for s in sentences:
                if not s.endswith("။"):
                    s += "။"
                params = urllib.parse.urlencode({
                    "ie": "UTF-8",
                    "q": s,
                    "tl": "my",
                    "client": "tw-ob"
                })
                url = f"https://translate.google.com/translate_tts?{params}"
                headers = {"User-Agent": "Mozilla/5.0"}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    audio, rate = sf.read(io.BytesIO(resp.read()), dtype="float32")
                    if audio.ndim > 1:
                        audio = audio.mean(axis=1)
                    sample_rate = rate
                    all_samples.append(audio)
            
            if not all_samples:
                return False
            
            full_audio = np.concatenate(all_samples)
            block = 1024
            with sd.OutputStream(samplerate=sample_rate, channels=1, dtype="float32") as out:
                for i in range(0, len(full_audio), block):
                    if self.stop_flag.is_set():
                        break
                    b = full_audio[i:i + block].astype("float32")
                    if on_level:
                        on_level(min(1.0, float(np.sqrt(np.mean(np.square(b)))) * 4))
                    out.write(b.reshape(-1, 1))
            return True
        except Exception as e:
            log("tts", f"{C['am']}Google Burmese TTS failed ({e}); falling back to Edge-TTS{C['x']}", "am")
            return False

    # ── Burmese TTS, primary is Gemini when a Google key is configured ──
    # Gemini has 30+ prebuilt voices and speaks Burmese; the older
    # texttospeech.googleapis.com does not. Falls back to Edge for a missing
    # key, a bad key or a network blip.

    # Persona → Gemini voice, chosen for a distinct character each. Face
    # config can override via voice.my_gemini.
    GEMINI_VOICES = {
        "aung": "Puck",         # young male, upbeat
        "hnin": "Aoede",        # young female, breezy
        "zaw":  "Charon",       # adult male, informative
        "mya":  "Kore",         # adult female, firm
        "uba":  "Sadaltager",   # older male, knowledgeable
    }
    GEMINI_DEFAULT = {"male": "Charon", "female": "Kore"}
    GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
    GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
                  "{model}:generateContent?key={key}")
    # Accept both key formats Google issues. AIzaSy… is the older one; AQ.…
    # is the format AI Studio has started giving out. A key that begins with
    # anything else is not a Google key and should not reach this endpoint.
    GOOGLE_KEY_PREFIXES = ("AIzaSy", "AQ.")

    @staticmethod
    def _looks_like_google_key(k):
        return isinstance(k, str) and any(
            k.startswith(p) for p in Mouth.GOOGLE_KEY_PREFIXES)

    def _synth_burmese_gemini(self, text):
        """Google Gemini TTS. Returns (audio, rate) or None."""
        import base64, urllib.request
        import numpy as np

        key = (bus.config().get("tts", {}) or {}).get("api_key", "").strip()
        if not self._looks_like_google_key(key):
            return None
        if time.time() < getattr(self, "_gemini_cooldown_until", 0):
            return None

        f = bus.face()
        fid = f.get("id", "")
        v = (f.get("voice") or {})
        gender = "female" if f.get("gender") == "female" else "male"
        voice_name = (v.get("my_gemini")
                      or self.GEMINI_VOICES.get(fid)
                      or self.GEMINI_DEFAULT[gender])

        # Gemini takes rate/pitch as instructions to the model, not as knobs.
        # Personas already differ by voice character, so nothing extra needed.
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice_name}
                    }
                },
            },
        }
        url = self.GEMINI_URL.format(model=self.GEMINI_MODEL, key=key)
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        last = None
        for attempt in range(SYNTH_TRIES):
            try:
                with urllib.request.urlopen(req, timeout=SYNTH_TIMEOUT) as r:
                    body = json.loads(r.read())
                cand = (body.get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                inline = parts[0].get("inlineData") if parts else None
                if not inline or not inline.get("data"):
                    # transient — the model sometimes returns finishReason
                    # OTHER with no audio, and retrying gets it
                    last = f"empty response ({cand.get('finishReason','?')})"
                    continue
                # audio/L16;codec=pcm;rate=24000 — signed 16-bit little-endian
                pcm = base64.b64decode(inline["data"])
                audio = np.frombuffer(pcm, dtype="<i2").astype("float32") / 32768.0
                mime = inline.get("mimeType", "")
                rate_hz = 24000
                if "rate=" in mime:
                    try:
                        rate_hz = int(mime.split("rate=")[1].split(";")[0])
                    except (ValueError, IndexError):
                        pass
                if attempt:
                    log("tts", f"{C['dim']}gemini recovered on attempt "
                               f"{attempt + 1}{C['x']}", "dim")
                return audio, rate_hz
            except urllib.error.HTTPError as e:
                # Terminal codes: no point burning attempts on a bad key or a
                # missing voice. 429 is terminal *for this reply*: retrying it
                # immediately just spends more of a quota that is already empty.
                if e.code in (400, 401, 403, 404):
                    detail = e.read()[:200].decode("utf-8", errors="replace")
                    log("tts", f"{C['am']}gemini refused ({e.code}): "
                               f"{detail}{C['x']}", "am")
                    return None
                if e.code == 429:
                    # Cool off long enough that the rest of this turn goes to
                    # Edge, and the next turn tries Gemini again. Free-tier
                    # quotas are per-minute so a minute is the right length.
                    self._gemini_cooldown_until = time.time() + 60
                    log("tts", f"{C['am']}gemini rate-limited (429); "
                               f"using Edge for the next minute{C['x']}", "am")
                    return None
                last = e
            except Exception as e:
                last = e
        log("tts", f"{C['am']}gemini failed after {SYNTH_TRIES} tries "
                   f"({last}); falling back to Edge{C['x']}", "am")
        return None

    def _synth_burmese(self, text):
        """Render Burmese to samples. Try Gemini first, fall back to Edge.

        A Google key sets the primary — 30+ voices instead of Edge's two — but
        the free Edge path is always there so a missing key, a bad key, or a
        network blip does not leave him mute.
        """
        got = self._synth_burmese_gemini(text)
        if got:
            return got
        return self._synth_burmese_edge_bytes(text)

    def _synth_burmese_edge_bytes(self, text):
        """Render Burmese via Microsoft Edge-TTS. Returns (audio, rate) or None.

        Free but only two voices exist — Thiha and Nilar — so five personas
        share them via rate and pitch. The primary path is Google Cloud when a
        key is configured; this is the fallback.
        """
        import asyncio, tempfile
        import numpy as np, soundfile as sf
        try:
            import edge_tts
        except ImportError:
            log("tts", f"{C['am']}edge-tts not installed; cannot speak Burmese{C['x']}", "am")
            return None

        f = bus.face()
        v = (f.get("voice") or {})
        gender = f.get("gender", "male")
        default_my = "my-MM-NilarNeural" if gender == "female" else "my-MM-ThihaNeural"
        voice = v.get("my", default_my)
        rate = v.get("my_rate", "-2%")
        pitch = v.get("my_pitch", "+0Hz")
        # A reply is several requests now rather than one, so a blip that used
        # to cost a whole answer once in a while now gets several chances to
        # land in the middle of one — and a missing piece sounds exactly like
        # Lugalay stopping half way. Transient failures come back on the next
        # attempt; only a real outage reaches the fallback voice.
        last = None
        for attempt in range(SYNTH_TRIES):
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            try:
                async def go():
                    # edge-tts has been seen to hang on a websocket that never
                    # connects. Without a bound, one bad connection stops the
                    # reply dead with no error and no sound.
                    await asyncio.wait_for(
                        edge_tts.Communicate(text, voice, rate=rate,
                                             pitch=pitch).save(tmp.name),
                        timeout=SYNTH_TIMEOUT)
                asyncio.run(go())
                audio, rate_hz = sf.read(tmp.name, dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                if attempt:
                    log("tts", f"{C['dim']}recovered on attempt {attempt + 1}{C['x']}",
                        "dim")
                return audio, rate_hz
            except Exception as e:
                last = e
                if attempt + 1 < SYNTH_TRIES:
                    time.sleep(0.4 * (attempt + 1))
            finally:
                os.path.exists(tmp.name) and os.unlink(tmp.name)

        log("tts", f"{C['am']}Edge-TTS voice unavailable after {SYNTH_TRIES} "
                   f"tries ({last}){C['x']}", "am")
        return None

    def _play(self, audio, rate_hz, on_level=None, text=""):
        """Push samples at the speakers, surviving a device that goes away."""
        import numpy as np, sounddevice as sd
        block = 1024
        try:
            with sd.OutputStream(samplerate=rate_hz, channels=1,
                                 dtype="float32") as out:
                for i in range(0, len(audio), block):
                    if self.stop_flag.is_set():
                        break
                    b = audio[i:i + block].astype("float32")
                    if on_level:
                        on_level(min(1.0, float(np.sqrt(np.mean(np.square(b)))) * 4))
                    out.write(b.reshape(-1, 1))
        except Exception as e:
            # Headphones pulled out mid-sentence, an output device switched, a
            # sample rate CoreAudio will not take — PortAudio raises, and this
            # used to travel all the way up and kill the voice loop, so one
            # unplugged cable ended the session until the app was restarted.
            log("tts", f"{C['am']}audio output failed ({e}); "
                       f"using the system voice{C['x']}", "am")
            text and self._say_fallback(text)
        return True

    def _speak_burmese_edge(self, text, on_level=None):
        """Synthesize Burmese using Microsoft's Native Neural Speech Model."""
        got = self._synth_burmese(text)
        if not got:
            return False
        return self._play(got[0], got[1], on_level, text)

    def _speak_burmese(self, text, on_level=None):
        """Synthesize Burmese using native Burmese neural speech models with SSML prosody."""
        text = format_burmese_for_speech(clean_spoken_text(text))
        if not text.strip():
            return True

        return self._speak_burmese_edge(text, on_level)

    def _say_fallback(self, text):
        """Last resort when Kokoro will not load. Ensure fallback voice matches
        the gender and age of the persona."""
        f = bus.face()
        gender = f.get("gender", "male")
        age = f.get("age", 25)
        try:
            if sys.platform == "darwin":
                if gender == "female":
                    voice = "Samantha" if age < 35 else "Karen"
                else:
                    voice = "Alex" if age < 55 else "Daniel"
                subprocess.run(["say", "-v", voice, text], check=False)
            elif sys.platform == "win32":
                hint = "Female" if gender == "female" else "Male"
                ps = ("Add-Type -AssemblyName System.Speech; "
                      "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                      f"$s.SelectVoiceByHints('{hint}'); "
                      f"$s.Speak(@'\n{text}\n'@)")
                subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
            else:
                subprocess.run(["espeak-ng", "-v", "en+f3" if gender == "female" else "en+m3", text], check=False)
        except (OSError, subprocess.SubprocessError) as e:
            log("tts", f"{C['am']}no fallback voice available ({e}){C['x']}", "am")

    def speak(self, text, on_level=None):
        self.stop_flag.clear()
        cleaned = clean_spoken_text(text)
        if not cleaned.strip():
            return

        # If the text contains Burmese, synthesize the entire response coherently
        # using the Burmese Neural Engine. This prevents jarring accent/voice hopping mid-sentence.
        if is_burmese(cleaned):
            self._speak_burmese(cleaned, on_level)
            on_level and on_level(0.0)
            return

        # Pure English response -> synthesize with Kokoro
        if self.kokoro is None:
            return self._say_fallback(cleaned)

        import numpy as np, sounddevice as sd
        for chunk in self._chunks(cleaned):
            if self.stop_flag.is_set():
                break
            try:
                f = bus.face()
                v = (f.get("voice") or {})
                gender = f.get("gender", "male")
                default_en = "af_heart" if gender == "female" else "am_adam"
                en_voice = v.get("en", default_en)
                samples, rate = self.kokoro.create(
                    chunk, voice=en_voice,
                    speed=float(self.cfg.get("speed", 1.0)), lang="en-us")
            except Exception as e:
                log("tts", f"{C['am']}kokoro failed mid-speech ({e}){C['x']}", "am")
                return self._say_fallback(chunk)

            block = 1024
            with sd.OutputStream(samplerate=rate, channels=1, dtype="float32") as out:
                for i in range(0, len(samples), block):
                    if self.stop_flag.is_set():
                        break
                    b = samples[i:i + block].astype("float32")
                    if on_level:
                        on_level(min(1.0, float(np.sqrt(np.mean(np.square(b)))) * 4))
                    out.write(b.reshape(-1, 1))
        on_level and on_level(0.0)

    # Streaming renders in units small enough that the next one is ready before
    # the current finishes. Whole-block speech deliberately never splits Burmese
    # (LIMIT_MY is 4000), and a 27-second blob takes ~5s to synthesise — long
    # enough to run the speakers dry and put a hole in the middle of the answer.
    # ~15 Burmese characters is about a second of speech, so this is roughly
    # six seconds a unit: long enough not to sound chopped, short enough that
    # rendering it (~0.8s) finishes well inside the previous unit's playback.
    STREAM_LIMIT_MY = 90

    @classmethod
    def _stream_units(cls, text):
        """Sentence-sized runs of Burmese, so nothing takes long to render."""
        out, buf = [], ""
        for sent in SENT.split(text.replace("\n", " ")):
            sent = sent.strip()
            if not sent:
                continue
            if buf and len(buf) + len(sent) < cls.STREAM_LIMIT_MY:
                buf = f"{buf} {sent}".strip()
            else:
                buf and out.append(buf)
                buf = sent
        buf and out.append(buf)
        return out or [text]

    def speak_burmese_stream(self, pieces, on_level=None):
        """Speak Burmese as the brain writes it, one sentence at a time.

        The whole reply used to be held back until the last word was generated,
        because splitting it by script sent each fragment to a different voice
        and the accent jumped around mid-sentence. That is not what this does:
        every piece here is Burmese and goes to the same Burmese voice, so
        nothing hops — he simply starts hearing the answer about six seconds
        sooner, which is most of the wait.

        A worker renders ahead while the speakers are busy, so the joins between
        sentences are silent rather than a pause per full stop.
        """
        self.stop_flag.clear()
        q = queue.Queue(maxsize=3)

        def render():
            try:
                for piece in pieces:
                    if self.stop_flag.is_set():
                        break
                    whole = format_burmese_for_speech(clean_spoken_text(piece))
                    if not whole.strip():
                        continue
                    # If a Google key is configured and Gemini is not on
                    # cooldown, send the whole piece as one request — Gemini's
                    # free tier is 10 RPM and each unit was another request.
                    key = (bus.config().get("tts", {}) or {}).get("api_key", "").strip()
                    gemini_up = (self._looks_like_google_key(key) and
                                 time.time() >= getattr(self,
                                     "_gemini_cooldown_until", 0))
                    units = [whole] if gemini_up else self._stream_units(whole)
                    for text in units:
                        if self.stop_flag.is_set():
                            break
                        got = self._synth_burmese(text)
                        if got:
                            q.put((got[0], got[1], text))
                        else:                   # network gone, voice refused
                            q.put((None, None, text))
            except Exception as e:
                log("tts", f"{C['am']}speech stream ended early ({e}){C['x']}", "am")
            finally:
                q.put(None)                     # nothing more is coming

        threading.Thread(target=render, daemon=True).start()

        while True:
            item = q.get()
            if item is None or self.stop_flag.is_set():
                break
            audio, rate_hz, text = item
            if audio is None:
                self._say_fallback(text)
            else:
                self._play(audio, rate_hz, on_level, text)
        on_level and on_level(0.0)

    def interrupt(self):
        self.stop_flag.set()


# ─────────────────────────── push to talk ────────────────────────────────
class PushToTalk:
    def __init__(self, cfg, events):
        from pynput import keyboard
        self.kb = keyboard
        self.events = events
        spec = cfg["mic"].get("key", "<cmd_r>")
        specs = spec if isinstance(spec, list) else [spec]
        try:
            self.keys = set()
            for one in specs:
                self.keys.update(keyboard.HotKey.parse(one))
        except Exception:
            log("mic", f"{C['am']}unknown key {spec!r}; falling back to right cmd{C['x']}", "am")
            self.keys = {keyboard.Key.cmd_r}
        self.spec = spec
        self.down = False
        self.saw_any_key = False
        self.debug = bool(cfg["mic"].get("debug_keys", True))
        self.noted = 0

    def _match(self, key):
        if key in self.keys:
            return True
        # Key.* enum members carry their vk on .value, not on the member, so
        # a naive getattr(key,"vk",None) yields None for both sides and makes
        # every modifier key match the talk key. Compare real vks only.
        def vk(k):
            v = getattr(k, "vk", None)
            if v is None:
                v = getattr(getattr(k, "value", None), "vk", None)
            return v
        mine = {v for v in (vk(k) for k in self.keys) if v is not None}
        return bool(mine) and vk(key) in mine

    def _note(self, key):
        """Log which MODIFIER keys arrive, so a wrong talk key is obvious.

        Deliberately never logs character keys — this file would otherwise be
        a keylogger, and the talk key is always a named key anyway.
        """
        if not self.debug or self.noted >= 12:
            return
        name = getattr(key, "name", None)
        if not name:                       # a character key: ignore it entirely
            return
        self.noted += 1
        if self.noted == 1:
            log("mic", f"{C['dim']}key monitoring is live{C['x']}")
        if not self._match(key):
            log("mic", f"{C['am']}saw <{name}> — not your talk key "
                       f"({self.spec}){C['x']}", "am")

    def on_press(self, key):
        self.saw_any_key = True
        self._note(key)
        if self._match(key) and not self.down:
            self.down = True
            self.events.put(("ptt_down", None))

    def on_release(self, key):
        if self._match(key) and self.down:
            self.down = False
            self.events.put(("ptt_up", None))

    @staticmethod
    def permission_problem():
        """Ask macOS directly instead of inferring from silence.

        Inferring "blocked" from "no keys pressed yet" cries wolf at anyone who
        simply reads the greeting before speaking. These two calls are the same
        checks the OS itself makes, so they are right the first time.

        Returns None when monitoring will work, otherwise a printable reason.
        """
        if sys.platform != "darwin":
            return None
        try:
            lib = ctypes.cdll.LoadLibrary(
                ctypes.util.find_library("ApplicationServices"))
            lib.AXIsProcessTrusted.restype = ctypes.c_bool
            if not lib.AXIsProcessTrusted():
                return "Accessibility"
        except Exception:
            pass                       # cannot check — assume fine, do not nag
        try:
            import Quartz
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
                lambda *a: None, None)
            if tap is None:
                return "Input Monitoring"
            Quartz.CFRelease(tap)
        except Exception:
            pass
        return None

    def run(self):
        problem = self.permission_problem()
        if problem:
            log("mic", f"{C['rd']}macOS is blocking the talk key "
                       f"({problem} not granted).{C['x']}", "rd")
            log("", f"Fix: System Settings ▸ Privacy & Security ▸ {problem},")
            log("", "add the terminal app you launched this from, then quit it")
            log("", "fully with Cmd-Q and start again. Closing the window is")
            log("", "not enough — permissions apply when the process starts.")
        listener = self.kb.Listener(on_press=self.on_press, on_release=self.on_release)
        listener.daemon = True
        listener.start()
        return listener


# ──────────────────────────────── the loop ───────────────────────────────
def check():
    ok = True
    print(f"\n{C['b']}Lugalay · dependency check{C['x']}\n")
    for label, fn in [
        ("sounddevice", lambda: __import__("sounddevice").query_devices()),
        ("faster-whisper", lambda: __import__("faster_whisper")),
        ("kokoro-onnx", lambda: __import__("kokoro_onnx")),
        ("pynput", lambda: __import__("pynput")),
        ("edge-tts (Burmese voice)", lambda: __import__("edge_tts")),
    ]:
        try:
            fn(); print(f"  {C['gr']}✓{C['x']} {label}")
        except Exception as e:
            ok = False; print(f"  {C['rd']}✗{C['x']} {label}: {e}")
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(MODELS, f)
        if os.path.exists(p):
            print(f"  {C['gr']}✓{C['x']} {f}  ({os.path.getsize(p)//(1024*1024)} MB)")
        else:
            ok = False; print(f"  {C['rd']}✗{C['x']} {f} missing")
    try:
        import sounddevice as sd
        ins = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
        print(f"  {C['gr']}✓{C['x']} microphones: {', '.join(ins[:3])}")
    except Exception as e:
        ok = False; print(f"  {C['rd']}✗{C['x']} microphone: {e}")
    r = subprocess.run(["claude", "-p", "Reply with exactly: ok",
                        "--output-format", "json"], cwd=HOME, env=Brain._env(),
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout)
        if d.get("is_error"):
            ok = False
            print(f"  {C['rd']}✗{C['x']} brain: {d.get('result')}")
        else:
            print(f"  {C['gr']}✓{C['x']} brain: {d.get('result','')[:40]}")
    except ValueError:
        ok = False; print(f"  {C['rd']}✗{C['x']} brain: no JSON from claude")
    print(f"\n{'all good' if ok else 'some pieces need attention'}\n")
    return 0 if ok else 1


def setkey():
    """Let the key introduce itself, instead of guessing what macOS calls it.

    Left command reports as <cmd> on macOS, right command as <cmd_r>, and which
    names a given keyboard produces is not worth anyone's afternoon.
    """
    from pynput import keyboard
    problem = PushToTalk.permission_problem()
    if problem:
        print(f"\n{C['rd']}macOS is blocking key monitoring ({problem}).{C['x']}")
        print(f"Grant it under Privacy & Security ▸ {problem}, Cmd-Q the "
              f"terminal, and try again.\n")
        return 1

    print(f"\n{C['b']}Pick your talk key{C['x']}\n")
    print("  Press and hold the key you want to talk with, then let go.")
    print(f"  {C['dim']}Pick one you never use in shortcuts — right command,")
    print(f"  right option, or a function key. Avoid plain left command:")
    print(f"  it is half of every shortcut on the machine.{C['x']}\n")

    picked = {}

    def on_press(k):
        name = getattr(k, "name", None)
        if not name:
            print(f"  {C['am']}that is a character key — pick a modifier or "
                  f"function key{C['x']}")
            return
        picked["spec"] = f"<{name}>"
        return False                        # stop the listener

    with keyboard.Listener(on_press=on_press) as lis:
        lis.join()

    spec = picked.get("spec")
    if not spec:
        print("  nothing captured.")
        return 1

    if spec == "<cmd>":
        print(f"\n  {C['am']}That is LEFT command. Every ⌘-shortcut you press "
              f"would start recording.{C['x']}")
        print("  Saving it anyway is a bad idea — run this again and use the "
              "RIGHT command key,")
        print("  or right option, or an F-key.\n")
        return 1

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["mic"]["key"] = spec
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"\n  {C['gr']}talk key set to {spec}{C['x']}")
    print(f"  saved to {CONFIG_PATH}")
    print("  restart Lugalay to use it.\n")
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--text", help="send this to the brain instead of listening")
    ap.add_argument("--say", help="speak this and exit (no brain, no mic)")
    ap.add_argument("--mock-brain", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--setkey", action="store_true",
                    help="hold the key you want as the talk key; it is saved")
    a = ap.parse_args()

    if a.check:
        return check()

    if a.setkey:
        return setkey()

    name, user = CFG.get("name", "Agent"), CFG.get("user", "there")
    mouth = Mouth(CFG)

    def level(v):
        bus.write("speaking", bus.read().get("text", ""), v)

    if a.say:
        bus.write("speaking", a.say, 0.5)
        mouth.speak(a.say, level)
        bus.write("idle")
        return 0

    brain = Brain(CFG.get("brain", {}), mock=a.mock_brain,
                  lang=CFG.get("language", {}).get("reply", "my"))
    # start pulling the local model into memory now rather than on his first
    # question; harmless and a no-op when the brain is Claude
    brain.warm_local()

    if a.text:
        bus.write("thinking", a.text)
        log("you", a.text, "cy")
        reply = brain.ask(a.text)
        log(name.lower(), reply, "gr")
        bus.write("speaking", reply, 0.4)
        mouth.speak(reply, level)
        bus.write("idle")
        return 0

    # full session
    # Ensure SIGTERM causes a clean exit when running standalone in main thread.
    # When running inside app.py on a worker thread, signal.signal cannot be
    # called and app.py's own reaper thread handles signals instead.
    if threading.current_thread() is threading.main_thread():
        try:
            signal.pthread_sigmask(signal.SIG_UNBLOCK,
                                   {signal.SIGTERM, signal.SIGINT, signal.SIGHUP})
        except (AttributeError, OSError):
            pass
        def _term_handler(sig, frame):
            raise KeyboardInterrupt
        try:
            signal.signal(signal.SIGTERM, _term_handler)
        except (ValueError, AttributeError):
            pass

    stt = Transcriber(CFG)
    events = queue.Queue()
    hands_free = CFG["mic"].get("mode", "ptt") == "open"

    def respond(said, lang=None):
        """One turn, shared by both microphone modes."""
        log("you", said, "cy")
        bus.write("thinking", said, 0.0)

        cfg = bus.config()

        # If he asked Lugalay to LOOK at something, take the photo before the
        # brain is called and hand it the path. Claude reads the image itself,
        # so there is no vision model here and no second round trip.
        asked = said
        if look is not None and look.wants_to_look(said):
            log("eyes", "looking...", "cy")
            asked = look.augment(said)
            if "could not be used" in asked:
                log("eyes", f"{C['am']}camera unavailable{C['x']}", "am")

        speak_mode = cfg.get("language", {}).get("reply", "my")
        if speak_mode == "my":
            target_lang = "my"
        elif speak_mode == "en":
            target_lang = "en"
        else:
            # Match Spoken Language
            target_lang = lang if lang in ("my", "en") else ("my" if is_burmese(said) else "en")

        is_my = (target_lang == "my") or is_burmese(said)
        streaming = CFG.get("brain", {}).get("stream", True)

        if not streaming:
            reply = brain.ask(asked, lang=target_lang)
            log(name.lower(), reply, "gr")
            bus.write("speaking", reply, 0.4)
            mouth.speak(reply, level)
            bus.write("idle")
            return

        if is_my:
            # Burmese, spoken as it is written. Measured on this machine: the
            # first sentence is ready 5.9s before the last one, and the reply
            # used to sit silent for all of it. Every piece goes to the same
            # Burmese voice, so the accent still never changes mid-answer.
            said_so_far = []

            def pieces():
                for piece, is_first in brain.stream(asked, lang=target_lang):
                    said_so_far.append(piece)
                    log(name.lower() if is_first else "", piece, "gr")
                    bus.write("speaking", " ".join(said_so_far), 0.4)
                    yield piece

            mouth.speak_burmese_stream(pieces(), level)
            bus.write("idle")
            return

        # For English: stream sentence-by-sentence with Kokoro
        said_parts = []
        for piece, first in brain.stream(asked, lang=target_lang):
            said_parts.append(piece)
            if first:
                log(name.lower(), piece, "gr")
            else:
                log("", piece, "gr")
            bus.write("speaking", piece, 0.4)
            mouth.speak(piece, level)
        bus.write("idle")

    def safe_respond(said, lang=None):
        """One turn, and never more than one turn, can fail.

        Everything in a turn is a moving part — a model that times out, a
        speech service that 500s, an audio device that vanishes. Letting any of
        them out of here stopped the loop dead and left a silent window that
        still looked alive.
        """
        try:
            respond(said, lang)
        except Exception as e:
            log("brain", f"{C['rd']}that turn failed ({type(e).__name__}: {e}); "
                         f"still listening{C['x']}", "rd")
            try:
                bus.write("error", "", 0.0)
                time.sleep(0.8)
                bus.write("idle")
            except Exception:
                pass

    if hands_free:
        mic = OpenMic(CFG, events)
        mic.start()
        threading.Thread(target=_open_meter, args=(mic,), daemon=True).start()
        print(f"\n{C['b']}{name}{C['x']} {C['dim']}· hands free, just talk "
              f"· ctrl-c to stop{C['x']}\n")
    else:
        ears = Ears(CFG)
        ptt = PushToTalk(CFG, events)
        ptt.run()
        key = CFG["mic"].get("key", "<cmd_r>")
        print(f"\n{C['b']}{name}{C['x']} {C['dim']}· hold {key} and speak "
              f"· ctrl-c to stop{C['x']}\n")

    tmpl = CFG.get("greeting") if CFG.get("language", {}).get("reply") == "my" \
        else CFG.get("greeting_en", CFG.get("greeting", "Hello {user}."))
    try:
        greeting = tmpl.format(user=user, name=name)
    except (KeyError, IndexError):
        greeting = tmpl
    bus.write("speaking", greeting, 0.4)
    log(name.lower(), greeting, "gr")
    mouth.speak(greeting, level)
    bus.write("idle")
    if hands_free:
        mic.listen()                       # only now, or it hears the greeting

    listening = False
    try:
        while True:
            kind, payload = events.get()

            if kind == "utterance":            # hands-free
                bus.write("thinking", "", 0.0)
                if not mic.is_speech(payload):
                    log("mic", f"{C['dim']}noise, not speech — ignored{C['x']}")
                    bus.write("idle"); mic.listen(); continue
                said, lang = stt(payload)
                if not said:
                    log("mic", "nothing caught", "am")
                    bus.write("idle"); mic.listen(); continue
                safe_respond(said, lang)
                mic.listen()

            elif kind == "ptt_down":
                if listening:
                    continue
                mouth.interrupt()          # barge-in: talking over me stops me
                listening = True
                ears.start()
                bus.write("listening", "", 0.0)
                threading.Thread(target=_meter, args=(ears, lambda: listening),
                                 daemon=True).start()
                log("mic", "listening …", "cy")

            elif kind == "ptt_up" and listening:
                listening = False
                audio = ears.stop()
                bus.write("thinking", "", 0.0)
                said, lang = stt(audio)
                if not said:
                    log("mic", "nothing caught", "am")
                    bus.write("idle")
                    continue
                safe_respond(said, lang)
    except KeyboardInterrupt:
        pass
    finally:
        bus.write("idle")
        print(f"\n{C['dim']}{name} stopped.{C['x']}")
    return 0


def _open_meter(mic):
    while True:
        if not mic.muted:
            bus.write("listening" if mic.speaking else bus.read().get("state", "idle"),
                      bus.read().get("text", ""), mic.level if mic.speaking else 0.0)
        time.sleep(0.08)


def _meter(ears, still):
    while still():
        bus.write("listening", "", ears.level)
        time.sleep(0.06)


if __name__ == "__main__":
    sys.exit(main())
