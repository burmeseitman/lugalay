#!/usr/bin/env python3
"""Lugalay's face. Serves the visualizer and exposes the bus over HTTP.

    python3 server.py [--no-open]
"""
import errno, json, os, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bus  # noqa: E402

CFG = bus.config()
PORT = int(CFG.get("face_port", 7317))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/state":
            return self._send(200, json.dumps(bus.read()))
        if path == "/config":
            return self._send(200, json.dumps({
                "name": CFG.get("name", "Agent"),
                "face": bus.face_id(),
                "faces": bus.faces(),
                "overlay": bool(CFG.get("window", {}).get("overlay", False)),
            }))
        if path == "/setup-defaults":
            import setup as setup_mod
            return self._send(200, json.dumps({
                "detected": setup_mod.detect_name(),
                "agent": CFG.get("name", "Lugalay"),
                "faces": bus.faces(),
            }))
        if path in ("/setup", "/setup.html"):
            with open(os.path.join(HERE, "setup.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path.split("?")[0] == "/setup":
            import setup as setup_mod
            n = int(self.headers.get("Content-Length", 0))
            try:
                answers = json.loads(self.rfile.read(n))
                result = setup_mod.apply(answers)
            except (ValueError, OSError) as e:
                return self._send(400, json.dumps({"error": str(e)}))
            return self._send(200, json.dumps(result, ensure_ascii=False))

        # the face is the one place the person can talk back to the agent:
        # picking a persona here also picks the voice it answers in
        if self.path.split("?")[0] != "/face":
            return self._send(404, json.dumps({"error": "not found"}))
        n = int(self.headers.get("Content-Length", 0))
        try:
            fid = json.loads(self.rfile.read(n)).get("id")
            bus.set_face(fid)
        except (ValueError, TypeError) as e:
            return self._send(400, json.dumps({"error": str(e)}))
        return self._send(200, json.dumps({"ok": True, "face": bus.face_id()}))

    def log_message(self, *a):
        pass  # the terminal belongs to the voice


def main():
    url = f"http://127.0.0.1:{PORT}/"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            print(f"face:  already running on {url} — reusing it", flush=True)
            return 0
        raise
    print(f"face:  {url}  ({CFG.get('face','board')})", flush=True)
    if "--no-open" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
