"""Build a one-image-at-a-time viewer for the reference images in ui pics/.

Stdlib only (no Pillow on this machine). Writes shots/refs.html with every
image embedded as a base64 data URI; append #N to the URL to show image N.
The Preview panel can then render each reference full-size.

Usage:
    python tools/refview.py
"""

import base64
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "ui pics")
OUT = os.path.join(ROOT, "shots", "refs.html")

files = []
for ext in ("*.jpeg", "*.jpg", "*.png"):
    files += glob.glob(os.path.join(SRC, ext))
files.sort()

parts = []
for i, path in enumerate(files):
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    parts.append(
        '<figure data-ref="%d">'
        '<figcaption>%d &nbsp;&middot;&nbsp; %s</figcaption>'
        '<img src="data:image/jpeg;base64,%s">'
        "</figure>" % (i + 1, i + 1, name, b64)
    )

html = """<!doctype html>
<html><head><meta charset="utf-8"><title>reference images</title>
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
      f.classList.toggle("on", f.dataset.ref === n);
    });
  }
  addEventListener("hashchange", show);
  show();
</script>
</body></html>
""" % "\n".join(parts)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html)

print("wrote %s (%d images)" % (OUT, len(files)))
for i, path in enumerate(files):
    print("  #%d %s" % (i + 1, os.path.basename(path)))
