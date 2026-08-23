#!/usr/bin/env python3
"""Render the app icon for all three platforms from the same pixel face.

Written by hand rather than with an image library so the build needs no extra
dependency, and so every logical pixel scales by a whole number — pixel art
that gets interpolated turns to mush.

    python3 packaging/make_icons.py     ->  build/icon.icns  .ico  .png
"""
import os
import shutil
import struct
import subprocess
import sys
import zlib

G = 28                       # logical grid
BG    = (13, 27, 34, 255)
SKIN  = (217, 162, 121, 255)
SHAD  = (184, 130, 92, 255)
HAIR  = (58, 43, 37, 255)
INK   = (32, 20, 26, 255)
WHT   = (244, 248, 249, 255)
SHIRT = (45, 96, 108, 255)
CLEAR = (0, 0, 0, 0)

HERE = os.path.dirname(os.path.abspath(__file__))


def face():
    px = [[CLEAR] * G for _ in range(G)]

    def rect(x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < G and 0 <= yy < G:
                    px[yy][xx] = c

    for y in range(G):                       # rounded plate
        inset = 3 if y in (0, G - 1) else 2 if y in (1, G - 2) else 1 if y in (2, G - 3) else 0
        rect(inset, y, G - 2 * inset, 1, BG)
    rect(6, 20, 16, 8, SHIRT)                # shoulders
    rect(12, 17, 4, 4, SHAD)                 # neck
    rect(8, 6, 12, 9, HAIR)                  # hair
    rect(9, 9, 10, 10, SKIN)                 # face
    rect(8, 11, 1, 4, SKIN)
    rect(19, 11, 1, 4, SKIN)                 # ears
    rect(9, 9, 10, 2, HAIR)                  # fringe
    rect(11, 12, 2, 2, WHT)
    rect(15, 12, 2, 2, WHT)                  # eyes
    rect(11, 12, 1, 1, INK)
    rect(15, 12, 1, 1, INK)                  # pupils
    rect(13, 14, 2, 1, SHAD)                 # nose
    rect(12, 16, 4, 1, INK)                  # mouth
    return px


PX = face()


def png_bytes(size):
    """A square PNG at `size`, nearest-neighbour so the pixels stay hard."""
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            row += bytes(PX[y * G // size][x * G // size])
        rows.append(bytes(row))
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def write_png(path, size):
    with open(path, "wb") as f:
        f.write(png_bytes(size))


def write_ico(path, sizes=(16, 32, 48, 64, 128, 256)):
    """ICO carrying PNG payloads — supported by Windows Vista and later."""
    images = [(s, png_bytes(s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        dim = 0 if size >= 256 else size          # 0 means 256 in an ICO
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(blob), offset)
        offset += len(blob)
        blobs += blob
    with open(path, "wb") as f:
        f.write(header + entries + blobs)


def write_icns(path):
    """macOS only: iconutil needs a real .iconset directory."""
    iconset = os.path.join(HERE, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    want = {"icon_16x16.png": 16, "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32, "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256, "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512, "icon_512x512@2x.png": 1024}
    for name, size in want.items():
        write_png(os.path.join(iconset, name), size)
    r = subprocess.run(["iconutil", "-c", "icns", iconset, "-o", path],
                       capture_output=True, text=True)
    shutil.rmtree(iconset, ignore_errors=True)
    if r.returncode:
        raise RuntimeError(f"iconutil failed: {r.stderr.strip()}")


def main():
    png = os.path.join(HERE, "icon.png")
    ico = os.path.join(HERE, "icon.ico")
    write_png(png, 512)
    write_ico(ico)
    print(f"  icon.png  {os.path.getsize(png)} bytes")
    print(f"  icon.ico  {os.path.getsize(ico)} bytes")
    if sys.platform == "darwin":
        icns = os.path.join(HERE, "icon.icns")
        write_icns(icns)
        print(f"  icon.icns {os.path.getsize(icns)} bytes")
    else:
        print("  icon.icns skipped (needs macOS)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
