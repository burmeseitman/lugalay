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
        if path == "/settings":
            cfg = bus.config()
            raw_key = (cfg.get("tts", {}).get("api_key") or "").strip()
            provider = "Free Edge-TTS"
            masked = ""
            if raw_key:
                if raw_key.startswith("sk-"):
                    provider = "OpenAI TTS (tts-1)"
                elif raw_key.startswith("AIzaSy"):
                    provider = "Google Cloud TTS"
                else:
                    provider = "ElevenLabs Multilingual v2"
                masked = ("•" * 16) + (raw_key[-4:] if len(raw_key) > 4 else "")
            return self._send(200, json.dumps({
                "user": cfg.get("user", ""),
                "agent": cfg.get("name", "Lugalay"),
                "listen_language": cfg.get("language", {}).get("listen", "my"),
                "speak_language": cfg.get("language", {}).get("reply", "my"),
                "face": bus.face_id(),
                "faces": bus.faces(),
                "has_api_key": bool(raw_key),
                "api_key_masked": masked,
                "provider": provider,
            }))
        if path == "/open-hands":
            import webbrowser
            hands_port = int(bus.config().get("hands_port", 7318))
            webbrowser.open(f"http://127.0.0.1:{hands_port}/")
            return self._send(200, json.dumps({"ok": True}))
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
        path = self.path.split("?")[0]
        if path == "/setup":
            import setup as setup_mod
            n = int(self.headers.get("Content-Length", 0))
            try:
                answers = json.loads(self.rfile.read(n))
                result = setup_mod.apply(answers)
            except (ValueError, OSError) as e:
                return self._send(400, json.dumps({"error": str(e)}))
            return self._send(200, json.dumps(result, ensure_ascii=False))

        if path == "/settings":
            n = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(n))
                cfg = bus.config()
                if "user" in data and data["user"].strip():
                    cfg["user"] = data["user"].strip()
                if "agent" in data and data["agent"].strip():
                    cfg["name"] = data["agent"].strip()
                if "listen_language" in data and data["listen_language"]:
                    cfg.setdefault("language", {})["listen"] = data["listen_language"]
                if "speak_language" in data and data["speak_language"]:
                    cfg.setdefault("language", {})["reply"] = data["speak_language"]
                if "language" in data and data["language"]:
                    cfg.setdefault("language", {})["reply"] = data["language"]
                if "face" in data and data["face"]:
                    bus.set_face(data["face"])
                if "api_key" in data:
                    new_key = data["api_key"].strip()
                    if not new_key.startswith("•"):
                        cfg.setdefault("tts", {})["api_key"] = new_key
                with open(bus.CONFIG, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return self._send(200, json.dumps({"ok": True, "face": bus.face_id()}))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))

        # the face is the one place the person can talk back to the agent:
        # picking a persona here also picks the voice it answers in
        if path != "/face":
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
