#!/usr/bin/env python3
"""Lugalay's hands: a board you move with your bare hands through the webcam.

Serves the board and persists it, so what you leave on the glass is still
there tomorrow. Everything (model + wasm) is vendored — no internet needed.

    python3 server.py [--no-open]
"""
import errno, json, mimetypes, os, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT)
import bus  # noqa: E402
sys.path.insert(0, HERE)
import open_url  # noqa: E402

CFG = bus.config()
PORT = int(CFG.get("hands_port", 7318))
BOARD = os.path.join(bus.ROOT, "hands", "state", "board.json")
LOCK = threading.Lock()


def load_board():
    try:
        with open(BOARD, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"cards": []}


def save_board(d):
    os.makedirs(os.path.dirname(BOARD), exist_ok=True)
    tmp = BOARD + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, BOARD)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self' 'unsafe-inline' blob: data:;")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if not bus.local_request(self.headers, PORT):
            return self._send(403, json.dumps({"error": "cross-site request refused"}))
        if path == "/board":
            with LOCK:
                return self._send(200, json.dumps(load_board()))
        if path == "/state":
            return self._send(200, json.dumps(bus.read()))
        if path == "/config":
            return self._send(200, json.dumps({"name": bus.config().get("name", "Agent")}))
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path.startswith("/vendor/"):
            rel = os.path.normpath(path[len("/vendor/"):]).lstrip("./")
            full = os.path.join(HERE, "vendor", rel)
            # never serve outside vendor/ — the trailing os.sep prevents
            # sibling directories named vendor_xxx from matching.
            vendor_dir = os.path.join(HERE, "vendor") + os.sep
            if not os.path.abspath(full).startswith(vendor_dir):
                return self._send(403, json.dumps({"error": "forbidden"}))
            if os.path.isfile(full):
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                if full.endswith(".wasm"):
                    ctype = "application/wasm"
                elif full.endswith(".mjs"):
                    ctype = "text/javascript"
                with open(full, "rb") as f:
                    return self._send(200, f.read(), ctype)
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = self.path.split("?")[0]
        if not bus.local_request(self.headers, PORT):
            return self._send(403, json.dumps({"error": "cross-site request refused"}))
        if path == "/open":
            # Opening a page is the one thing Lugalay can do to the machine, and
            # it lives here rather than in a shell command on purpose: a voice
            # session cannot approve anything, so the alternative was handing
            # the brain `open`/`xdg-open` outright. Here the address is checked
            # in-process and only http(s) ever reaches the platform opener.
            n = min(int(self.headers.get("Content-Length", 0) or 0), 8 * 1024)
            try:
                want = json.loads(self.rfile.read(n)).get("url", "")
            except ValueError:
                return self._send(400, json.dumps({"error": "bad request"}))
            url, err = open_url.normalise(want)
            if err:
                return self._send(400, json.dumps({"error": err}))
            try:
                open_url.open_url(url)
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
            return self._send(200, json.dumps({"ok": True, "opened": url}))

        if path == "/look":
            # The eyes live in the app, and in a packaged install there is no
            # agent/eyes on disk and no interpreter to run it with — so this is
            # the only way Lugalay can take a look on his own initiative rather
            # than only when the voice loop does it for him. It also means the
            # camera is opened by the app itself, which is the identity macOS
            # attaches the permission to.
            try:
                sys.path.insert(0, os.path.join(AGENT, "eyes"))
                import look as eyes_look
                p_, err = eyes_look.capture()
            except Exception as e:
                return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))
            if err:
                return self._send(503, json.dumps({"error": err}))
            return self._send(200, json.dumps({"ok": True, "frame": p_}))

        if path != "/board":
            return self._send(404, json.dumps({"error": "not found"}))
        n = min(int(self.headers.get("Content-Length", 0) or 0), 1024 * 1024)
        try:
            d = json.loads(self.rfile.read(n))
            assert isinstance(d.get("cards"), list)
        except (ValueError, AssertionError):
            return self._send(400, json.dumps({"error": "bad board"}))
        with LOCK:
            save_board(d)
        self._send(200, json.dumps({"ok": True, "cards": len(d["cards"])}))

    def log_message(self, *a):
        pass


def main():
    url = f"http://127.0.0.1:{PORT}/"
    if not os.path.exists(BOARD):
        save_board({"cards": []})
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            print(f"hands:  already running on {url} — reusing it", flush=True)
            return 0
        raise
    print(f"hands: {url}  (open in a browser when you want the board)", flush=True)
    if "--no-open" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
