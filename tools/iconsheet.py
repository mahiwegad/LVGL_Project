"""iconsheet.py - dump the embedded home icon bitmaps as PNGs for review.

home_icons.h holds six RGB565 LVGL image descriptors cropped from the supplied
reference photo. This script re-parses their C arrays (no compiler needed) and
writes a scaled contact sheet so the crops can be judged at 1:1 and enlarged.

Usage:
    python tools/iconsheet.py
"""

import base64
import os
import re
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from bmp2png import write_png  # noqa: E402


def parse_icons(path):
    """Return [(name, w, h, [(r,g,b), ...])] for each descriptor in the header."""
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()

    icons = []

    # Each icon is a uint8_t array named <name>_map followed by an
    # lv_image_dsc_t named <name> that carries width/height.
    for m in re.finditer(
        r"static const uint8_t (\w+)_map\[\] = \{(.*?)\};", text, re.S
    ):
        name, body = m.group(1), m.group(2)

        # Find the matching descriptor for the dimensions.
        d = re.search(
            r"static const lv_image_dsc_t %s = \{(.*?)\};" % re.escape(name),
            text,
            re.S,
        )
        if not d:
            continue

        w = int(re.search(r"\.header\.w = (\d+)", d.group(1)).group(1))
        h = int(re.search(r"\.header\.h = (\d+)", d.group(1)).group(1))

        values = [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]{2})", body)]
        assert len(values) % 2 == 0, (name, len(values))

        pixels = []
        for i in range(0, len(values), 2):
            lo, hi = values[i], values[i + 1]
            px = (hi << 8) | lo          # little-endian 16-bit word
            r = (px >> 11) & 0x1F
            g = (px >> 5) & 0x3F
            b = px & 0x1F
            pixels.append(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))

        icons.append((name, w, h, pixels))

    return icons


def to_png(icon, scale):
    name, w, h, pixels = icon
    ow, oh = w * scale, h * scale
    rows = []
    for y in range(oh):
        row = bytearray()
        for x in range(ow):
            r, g, b = pixels[(y // scale) * w + (x // scale)]
            row += bytes((r, g, b))
        rows.append(bytes(row))
    return ow, oh, rows


def main():
    icons = parse_icons(os.path.join(ROOT, "home_icons.h"))
    print("parsed %d icons" % len(icons))

    tiles = []
    for icon in icons:
        scale = 3
        w, h, rows = to_png(icon, scale)
        png_path = os.path.join(ROOT, "shots", "icon_%s.png" % icon[0])
        write_png(png_path, w, h, rows)
        with open(png_path, "rb") as handle:
            b64 = base64.b64encode(handle.read()).decode()
        tiles.append((icon[0], icon[1], icon[2], b64))
        print("  %-22s %dx%d -> %s" % (icon[0], icon[1], icon[2], png_path))

    cards = "".join(
        '<figure><img src="data:image/png;base64,%s"><figcaption>%s (%dx%d)</figcaption></figure>'
        % (b64, name, w, h)
        for name, w, h, b64 in tiles
    )

    html = (
        "<!doctype html><meta charset=utf-8><title>home icons</title>"
        "<style>body{background:#fff;font:13px system-ui;margin:16px}"
        "figure{display:inline-block;margin:8px;text-align:center}"
        "img{image-rendering:pixelated;border:1px solid #ccc}</style>"
        "<h2>Embedded home icons (3x nearest neighbour)</h2>%s" % cards
    )

    out = os.path.join(ROOT, "shots", "icons.html")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(html)
    print("wrote", out)


if __name__ == "__main__":
    main()
