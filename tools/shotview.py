"""Contact sheet of every BMP in shots/, viewable one at a time.

Reuses bmp2png.py's stdlib BMP decoder (no Pillow on this machine) and writes
shots/index.html with each render embedded as a base64 PNG data URI. Append
#N to the URL to show image N - the same viewer the reference images use.

Usage:
    python tools/shotview.py
"""

import base64
import glob
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)

from bmp2png import read_bmp  # noqa: E402

OUT = os.path.join(ROOT, "shots", "index.html")


def encode_png(width, height, rows):
    """8-bit truecolour PNG, filter type 0 on every row (same as bmp2png)."""
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

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    return png

files = sorted(glob.glob(os.path.join(ROOT, "shots", "*.bmp")))

parts = []
for i, path in enumerate(files):
    name = os.path.basename(path)
    width, height, rows = read_bmp(path)
    b64 = base64.b64encode(encode_png(width, height, rows)).decode("ascii")
    parts.append(
        '<figure data-shot="%d">'
        '<figcaption>%d &nbsp;&middot;&nbsp; %s (%dx%d)</figcaption>'
        '<img src="data:image/png;base64,%s">'
        "</figure>" % (i + 1, i + 1, name, width, height, b64)
    )

html = """<!doctype html>
<html><head><meta charset="utf-8"><title>simulator renders</title>
<style>
  html, body { margin:0; height:100%%; background:#0b0f13; color:#e6edf3;
               font:13px/1.4 Segoe UI, system-ui, sans-serif; overflow:hidden; }
  figure { position:absolute; inset:0; margin:0; padding:0; display:none; }
  figure.on { display:block; }
  figcaption { position:absolute; top:3px; left:0; right:0; text-align:center;
               color:#7dd3fc; font-weight:600; }
  img { position:absolute; inset:22px 4px 4px; width:calc(100%% - 8px);
        height:calc(100%% - 26px); object-fit:contain; }
</style></head><body>
%s
<script>
  function show() {
    var n = (location.hash || "#1").slice(1);
    document.querySelectorAll("figure").forEach(function (f) {
      f.classList.toggle("on", f.dataset.shot === n);
    });
  }
  addEventListener("hashchange", show);
  show();
</script>
</body></html>
""" % "\n".join(parts)

with open(OUT, "w", encoding="utf-8") as handle:
    handle.write(html)

print("wrote %s (%d renders)" % (OUT, len(files)))
for i, path in enumerate(files):
    print("  #%d %s" % (i + 1, os.path.basename(path)))
