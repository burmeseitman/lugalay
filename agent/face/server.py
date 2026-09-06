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
        if not bus.local_request(self.headers, PORT):
            return self._send(403, json.dumps({"error": "cross-site request refused"}))
        if path == "/state":
            return self._send(200, json.dumps(bus.read()))
        if path == "/config":
            # read it fresh: CFG is a snapshot from start-up, so after the
            # settings page saved a new name this went on serving the old one
            live = bus.config()
            return self._send(200, json.dumps({
                "name": live.get("name", "Agent"),
                "face": bus.face_id(),
                "faces": bus.faces(),
                "overlay": bool(live.get("window", {}).get("overlay", False)),
            }))
        if path == "/settings":
            cfg = bus.config()
            tts = cfg.get("tts", {})
            return self._send(200, json.dumps({
                "user": cfg.get("user", ""),
                "agent": cfg.get("name", "Lugalay"),
                "listen_language": cfg.get("language", {}).get("listen", "my"),
                "speak_language": cfg.get("language", {}).get("reply", "my"),
                "face": bus.face_id(),
                "faces": bus.faces(),
                # Never send the key back to the browser, even over loopback.
                "gemini_key_saved": bool(
                    tts.get("gemini_api_key") or tts.get("api_key")),
                "gemini_key_from_environment": bool(
                    os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
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
                "agent": cfg.get("name", "Lugalay"),
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
        if not bus.local_request(self.headers, PORT):
            return self._send(403, json.dumps({"error": "cross-site request refused"}))
        if path == "/setup":
            import setup as setup_mod
            n = min(int(self.headers.get("Content-Length", 0) or 0), 64 * 1024)
            try:
                answers = json.loads(self.rfile.read(n))
                result = setup_mod.apply(answers)
            except (ValueError, OSError) as e:
                return self._send(400, json.dumps({"error": str(e)}))
            return self._send(200, json.dumps(result, ensure_ascii=False))

        if path == "/settings":
            n = min(int(self.headers.get("Content-Length", 0) or 0), 64 * 1024)
            try:
                data = json.loads(self.rfile.read(n))
                cfg = bus.config()
                # names go into prompts and onto the screen; a megabyte of
                # them helps nobody and bloats every turn the brain takes
                def name(v):
                    return str(v).strip()[:60]
                if "user" in data and name(data["user"]):
                    cfg["user"] = name(data["user"])
                if "agent" in data and name(data["agent"]):
                    cfg["name"] = name(data["agent"])
                if "listen_language" in data and data["listen_language"]:
                    cfg.setdefault("language", {})["listen"] = data["listen_language"]
                if "speak_language" in data and data["speak_language"]:
                    cfg.setdefault("language", {})["reply"] = data["speak_language"]
                if "language" in data and data["language"]:
                    cfg.setdefault("language", {})["reply"] = data["language"]
                if "face" in data and data["face"]:
                    bus.set_face(data["face"])
                if ("gemini_api_key" in data
                        or data.get("clear_gemini_api_key")):
                    import setup as setup_mod
                    setup_mod.set_gemini_api_key(
                        cfg,
                        data.get("gemini_api_key"),
                        clear=bool(data.get("clear_gemini_api_key")),
                    )
                bus.save_config(cfg)
                tts = cfg.get("tts", {})
                return self._send(200, json.dumps({
                    "ok": True,
                    "face": bus.face_id(),
                    "gemini_key_saved": bool(
                        tts.get("gemini_api_key") or tts.get("api_key")),
                }))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))

        # the face is the one place the person can talk back to the agent:
        # picking a persona here also picks the voice it answers in
        if path != "/face":
            return self._send(404, json.dumps({"error": "not found"}))
        n = min(int(self.headers.get("Content-Length", 0) or 0), 64 * 1024)
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
    print(f"face:  {url}  ({CFG.get('face','aung')})", flush=True)
    if "--no-open" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
