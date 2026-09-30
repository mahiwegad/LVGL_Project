"""bmp2png.py - convert the LVGL screenshot BMP into a viewable PNG + HTML.

The simulator can render its screen to a 24-bit BMP (see ``--shot`` in main.c).
Pillow is not installed here, so this uses only the standard library: ``zlib``
for the PNG's deflate stream and ``struct`` for the chunk headers.

It also writes an HTML page with the PNG embedded as a base64 data URI, so the
render can be opened in the browser preview without relying on relative file
serving.

Usage:
    python tools/bmp2png.py shots/home.bmp
"""

import base64
import os
import struct
import sys
import zlib


def read_bmp(path):
    """Return (width, height, rows) with rows as top-down RGB bytes."""
    with open(path, "rb") as handle:
        data = handle.read()

    if data[:2] != b"BM":
        raise ValueError(f"{path} is not a BMP")

    offset = struct.unpack_from("<I", data, 10)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    bpp = struct.unpack_from("<H", data, 28)[0]

    if bpp != 24:
        raise ValueError(f"expected a 24-bit BMP, got {bpp} bpp")

    bottom_up = height > 0
    height = abs(height)
    stride = (width * 3 + 3) & ~3

    rows = []
    for y in range(height):
        start = offset + y * stride
        raw = data[start:start + width * 3]
        # BMP stores BGR; PNG wants RGB.
        rgb = bytearray(width * 3)
        rgb[0::3] = raw[2::3]
        rgb[1::3] = raw[1::3]
        rgb[2::3] = raw[0::3]
        rows.append(bytes(rgb))

    if bottom_up:
        rows.reverse()

    return width, height, rows


def write_png(path, width, height, rows):
    """Write an 8-bit truecolour PNG (filter type 0 on every row)."""
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)

    def chunk(tag, payload):
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", header)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")

    with open(path, "wb") as handle:
        handle.write(png)

    return png


def write_html(path, png_bytes, width, height, caption):
    encoded = base64.b64encode(png_bytes).decode("ascii")

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{caption}</title>
<style>
  body {{ margin: 0; background: #334155; font: 13px system-ui, sans-serif; }}
  .wrap {{ padding: 12px; }}
  .cap {{ color: #e2e8f0; margin-bottom: 8px; }}
  img {{ display: block; width: {width}px; height: {height}px;
         image-rendering: pixelated; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="cap">{caption} — {width}x{height}, rendered by LVGL</div>
  <img src="data:image/png;base64,{encoded}" alt="{caption}">
</div>
</body>
</html>
"""

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1

    bmp_path = argv[1]
    base = os.path.splitext(bmp_path)[0]

    width, height, rows = read_bmp(bmp_path)
    png_bytes = write_png(base + ".png", width, height, rows)

    write_html(
        base + ".html",
        png_bytes,
        width,
        height,
        os.path.basename(base),
    )

    print(f"{bmp_path} -> {base}.png ({width}x{height}) -> {base}.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
