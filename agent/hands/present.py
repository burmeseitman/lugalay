#!/usr/bin/env python3
"""Put something on Lugalay's board.

    python3 present.py "a note in his own words"
    python3 present.py --image ~/Desktop/chart.png --title "Q3"
    python3 present.py --clear
    python3 present.py --list

This is the `present` verb: when he asks to SEE something, Lugalay
puts it on the glass instead of reading it out loud.
"""
import argparse, base64, json, mimetypes, os, random, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bus  # noqa: E402

PORT = int(bus.config().get("hands_port", 7318))
BASE = f"http://127.0.0.1:{PORT}"
BOARD = os.path.join(HERE, "state", "board.json")
TINTS = ["#39d0d8", "#52e39f", "#f0a830", "#c58af0", "#f07a7a"]


def get():
    try:
        with urllib.request.urlopen(f"{BASE}/board", timeout=3) as r:
            return json.load(r), True
    except Exception:
        try:
            with open(BOARD) as f:
                return json.load(f), False
        except (OSError, ValueError):
            return {"cards": []}, False


def put(d, live):
    if live:
        req = urllib.request.Request(f"{BASE}/board", data=json.dumps(d).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=3):
            return
    os.makedirs(os.path.dirname(BOARD), exist_ok=True)
    with open(BOARD, "w") as f:
        json.dump(d, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--image")
    ap.add_argument("--title", default="")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    d, live = get()

    if a.clear:
        d["cards"] = []
        put(d, live); print("board cleared")
        return 0
    if a.list:
        for c in d["cards"]:
            print(f"  {c['id']}  {c['kind']:5}  {(c.get('title') or c.get('text',''))[:60]}")
        print(f"({len(d['cards'])} cards)")
        return 0

    card = {"id": f"c{random.randint(100000, 999999)}",
            "x": round(random.uniform(0.18, 0.62), 3),
            "y": round(random.uniform(0.18, 0.55), 3),
            "tint": random.choice(TINTS), "title": a.title}

    if a.image:
        p = os.path.expanduser(a.image)
        if not os.path.isfile(p):
            print(f"no such image: {p}", file=sys.stderr)
            return 1
        mime = mimetypes.guess_type(p)[0] or "image/png"
        with open(p, "rb") as f:
            card.update(kind="image", w=0.26, h=0.26,
                        src=f"data:{mime};base64,{base64.b64encode(f.read()).decode()}")
    elif a.text:
        card.update(kind="note", text=a.text, w=0.22, h=0.18)
    else:
        print("nothing to present — give me text or --image", file=sys.stderr)
        return 1

    d["cards"].append(card)
    put(d, live)
    print(f"presented {card['kind']} {card['id']}"
          f"{' (board is not running; saved for next launch)' if not live else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
