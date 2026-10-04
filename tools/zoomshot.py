"""Zoom one region of a rendered shot so small text can be judged for clipping.

The contact sheet (shotview.py) shows a whole 800x480 render at roughly its
native size, which is too small to tell a tight fit from a clipped glyph. This
tool crops a rectangle out of a shot and scales it up with nearest-neighbour,
writing a standalone page at shots/zoom_shot.html (served next to index.html).

Usage:
    python tools/zoomshot.py <shot.bmp> <x> <y> <w> <h> [scale]

Everything is stdlib: bmp2png already has the BMP decoder and PNG encoder.
"""

import base64
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)

from bmp2png import read_bmp  # noqa: E402

OUT = os.path.join(ROOT, "shots", "zoom_shot.html")


def encode_png(width, height, rows):
    """8-bit truecolour PNG, filter type 0 on every row."""
    raw = bytearray()

    for row in rows:
        raw.append(0)
        raw += row

    def chunk(tag, payload):
        body = tag + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def crop_scale(rows, x, y, w, h, scale):
    """Nearest-neighbour crop + scale, returning (width, height, rows)."""
    out = []

    for sy in range(h):
        src = rows[y + sy]
        line = bytearray()

        for sx in range(w):
            px = src[(x + sx) * 3:(x + sx) * 3 + 3]
            line += px * scale

        for _ in range(scale):
            out.append(bytes(line))

    return w * scale, h * scale, out


def main():
    if len(sys.argv) < 6:
        print(__doc__)
        return 1

    path = sys.argv[1]
    x, y, w, h = (int(v) for v in sys.argv[2:6])
    scale = int(sys.argv[6]) if len(sys.argv) > 6 else 2

    width, height, rows = read_bmp(path)

    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))

    zw, zh, zrows = crop_scale(rows, x, y, w, h, scale)
    png = encode_png(zw, zh, zrows)
    data = base64.b64encode(png).decode("ascii")

    title = f"{os.path.basename(path)}  crop {x},{y} {w}x{h} x{scale}"
    src = "data:image/png;base64," + data

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  html, body {{ margin:0; padding:0; background:#0b0b0f; color:#e6e6ee;
                font:13px/1.4 system-ui, sans-serif; }}
  h1 {{ font-size:14px; font-weight:600; margin:6px 10px; }}
  img {{ display:block; margin:0 10px 12px; image-rendering:pixelated;
         background:#fff; }}
</style></head>
<body>
<h1>{title}</h1>
<img src="{src}" width="{zw}" height="{zh}">
</body></html>
"""

    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(html)

    print(f"wrote {OUT}  ({zw}x{zh})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
