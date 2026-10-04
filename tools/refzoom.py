"""Zoomed crops of the device photos in ui pics/.

The 2026-09-30 references are photographs of a monitor, so the UI text is only
a few pixels tall in the original. This renders hand-picked regions blown up,
stacked on one scrollable page, so they can actually be read in the Preview
panel.

Stdlib only. Crops are stated in the natural pixel coordinates of the source
image, which are printed on each caption so they are easy to adjust.

Usage:
    python tools/refzoom.py
"""

import base64
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "ui pics")
OUT = os.path.join(ROOT, "shots", "zoom.html")

# On-screen width every crop is blown up to.
BOX_W = 1000

# (image basename fragment, x, y, w, h, caption) in natural source pixels.
CROPS = [
    ("4.40.10 PM.jpeg",        110, 440, 750, 180, "1a  LIST OF TESTS - title + card grid"),
    ("4.40.10 PM.jpeg",        110, 735, 750, 120, "1b  LIST OF TESTS - bottom bar"),
    ("4.40.11 PM (1).jpeg",    130, 490, 730, 215, "2a  MEASUREMENT - header + chart"),
    ("4.40.11 PM (1).jpeg",    130, 680, 730, 135, "2b  MEASUREMENT - readouts + action bar"),
    ("4.40.11 PM (2).jpeg",    120, 380, 750, 105, "3a  RESULTS - title + filters"),
    ("4.40.11 PM (2).jpeg",    120, 455, 750, 205, "3b  RESULTS - saved-run cards"),
    ("4.40.11 PM (2).jpeg",    120, 715, 750, 120, "3c  RESULTS - bottom bar"),
]

files = {os.path.basename(p): p for p in glob.glob(os.path.join(SRC, "*"))}

parts = []
for i, (frag, x, y, w, h, caption) in enumerate(CROPS):
    match = next((p for name, p in files.items() if frag in name), None)
    if match is None:
        print("  ! no image for", frag)
        continue

    with open(match, "rb") as handle:
        b64 = base64.b64encode(handle.read()).decode("ascii")

    scale = BOX_W / w
    box_h = int(h * scale)

    parts.append(
        '<figure id="c%d">'
        '<figcaption>%s <span class="src">crop %d,%d %dx%d of %s</span></figcaption>'
        '<div class="frame" style="width:%dpx;height:%dpx">'
        '<img src="data:image/jpeg;base64,%s" '
        'style="transform:translate(%dpx,%dpx) scale(%.4f)">'
        "</div></figure>"
        % (
            i + 1, caption, x, y, w, h, os.path.basename(match),
            BOX_W, box_h, b64, -int(x * scale), -int(y * scale), scale,
        )
    )

html = """<!doctype html>
<html><head><meta charset="utf-8"><title>reference zoom</title>
<style>
  body { margin:0; background:#0b0f13; color:#e6edf3;
         font:13px/1.4 Segoe UI, system-ui, sans-serif; }
  figure { margin:0; padding:8px 12px 20px; }
  figcaption { color:#7dd3fc; font-weight:600; margin-bottom:5px; }
  .src { color:#64748b; font-weight:400; }
  .frame { position:relative; overflow:hidden;
           border:1px solid #30363d; background:#fff; }
  .frame img { position:absolute; top:0; left:0; transform-origin:0 0;
               image-rendering:pixelated; }
</style></head><body>
%s
</body></html>
""" % "\n".join(parts)

with open(OUT, "w", encoding="utf-8") as handle:
    handle.write(html)

print("wrote %s (%d crops)" % (OUT, len(parts)))
for i, crop in enumerate(CROPS):
    print("  #%d %s" % (i + 1, crop[5]))
