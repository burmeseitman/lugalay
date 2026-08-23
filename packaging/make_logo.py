#!/usr/bin/env python3
"""Draw the project logo as an SVG, from the same pixel face the app shows.

SVG rather than PNG so it stays sharp at any size, stays small, and diffs as
text. Horizontal runs of identical pixels are merged into single rects, which
takes the file from a few thousand elements to a few hundred.

The plate is dark and self-contained, so the logo reads the same on GitHub's
light and dark themes without needing two files.

    python3 packaging/make_logo.py     ->  assets/logo.svg
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

# ── palette: the same one the avatar uses on screen ──
SKIN  = "#d9a279"
SHADE = "#b8825c"
HAIR  = "#33261f"
HAIRHI = "#4a382f"
INK   = "#20141a"
WHITE = "#f4f8f9"
SHIRT = "#2d606c"
BLUSH = "#e0664f"
ACCENT = "#39d0d8"
PLATE = "#0b1519"

G = 34                      # the face grid
grid = [[None] * G for _ in range(G)]


def rect(x, y, w, h, c):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= xx < G and 0 <= yy < G:
                grid[yy][xx] = c


# ── shoulders, neck ──
rect(4, 28, 26, 6, SHIRT)
rect(6, 27, 22, 1, SHIRT)
rect(14, 24, 6, 4, SHADE)

# ── head ──
rect(9, 7, 16, 19, SKIN)
rect(10, 6, 14, 1, SKIN)
rect(10, 26, 14, 1, SKIN)

# ── ears ──
rect(7, 15, 2, 4, SKIN)
rect(25, 15, 2, 4, SKIN)
rect(8, 16, 1, 2, SHADE)
rect(25, 16, 1, 2, SHADE)

# ── hair: cap, fringe, sides ──
rect(9, 4, 16, 5, HAIR)
rect(10, 3, 14, 1, HAIR)
rect(8, 6, 2, 8, HAIR)
rect(24, 6, 2, 8, HAIR)
rect(9, 9, 16, 2, HAIR)
rect(12, 4, 7, 1, HAIRHI)

# ── brows ──
rect(11, 12, 4, 1, HAIR)
rect(19, 12, 4, 1, HAIR)

# ── eyes: white, pupil, catchlight ──
for ex in (11, 19):
    rect(ex, 14, 4, 4, WHITE)
    rect(ex + 1, 15, 2, 2, INK)
    rect(ex + 1, 15, 1, 1, WHITE)

# ── nose ──
rect(16, 18, 2, 2, SHADE)
rect(15, 20, 4, 1, SHADE)

# ── blush ──
rect(10, 19, 3, 2, BLUSH)
rect(21, 19, 3, 2, BLUSH)

# ── smile ──
rect(14, 22, 6, 1, INK)
rect(13, 21, 1, 1, INK)
rect(20, 21, 1, 1, INK)


def runs(px):
    """Merge each row's identical neighbours into one rect."""
    out = []
    for y in range(G):
        x = 0
        while x < G:
            c = grid[y][x]
            if c is None:
                x += 1
                continue
            w = 1
            while x + w < G and grid[y][x + w] == c:
                w += 1
            out.append((x * px, y * px, w * px, px, c))
            x += w
    return out


def build():
    PX = 11                                  # pixel size in the logo
    face_w = G * PX                          # 374
    pad = 30
    W, H = 900, face_w + pad * 2             # 900 x 434 -> trimmed below
    H = face_w + pad * 2

    body = []
    body.append(f'<rect width="{W}" height="{H}" rx="26" fill="{PLATE}"/>')
    body.append(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="25" '
                f'fill="none" stroke="{ACCENT}" stroke-opacity=".14"/>')

    # the avatar, with a soft glow behind it
    body.append(f'<g transform="translate({pad},{pad})">')
    body.append(f'<ellipse cx="{face_w/2}" cy="{face_w*0.62}" rx="{face_w*0.42}" '
                f'ry="{face_w*0.34}" fill="{ACCENT}" opacity=".10"/>')
    for x, y, w, h, c in runs(PX):
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c}"/>')
    body.append("</g>")

    # wordmark
    tx = pad + face_w + 46
    mono = ("ui-monospace,'SF Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace")
    body.append(
        f'<text x="{tx}" y="{H*0.42}" font-family="{mono}" font-size="76" '
        f'font-weight="700" letter-spacing="4" fill="{WHITE}">Lugalay</text>')
    body.append(
        f'<text x="{tx+4}" y="{H*0.55}" font-family="{mono}" font-size="21" '
        f'letter-spacing="3.4" fill="{ACCENT}" fill-opacity=".85">'
        f'A PERSONAL AI THAT LISTENS</text>')
    body.append(
        f'<text x="{tx+4}" y="{H*0.68}" font-family="{mono}" font-size="18" '
        f'letter-spacing="1.2" fill="{WHITE}" fill-opacity=".45">'
        f'voice · memory · a face · hands</text>')
    body.append(
        f'<rect x="{tx+4}" y="{H*0.75}" width="150" height="3" rx="1.5" '
        f'fill="{ACCENT}" opacity=".55"/>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'width="{W}" height="{H}" role="img" aria-label="Lugalay">\n  '
           + "\n  ".join(body) + "\n</svg>\n")

    os.makedirs(ASSETS, exist_ok=True)
    out = os.path.join(ASSETS, "logo.svg")
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    return out, len(svg), svg.count("<rect")


if __name__ == "__main__":
    path, size, rects = build()
    print(f"  {os.path.relpath(path, os.path.dirname(HERE))}  "
          f"{size} bytes, {rects} rects")
