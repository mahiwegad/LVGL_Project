"""makeicons.py - cut the six home icons out of the reference artwork.

The home menu's keys are illustrated blue tiles. This finds the six blue tiles
in the supplied reference render, crops each one, box-averages it down to the
size the panel actually draws, and emits ``home_icons.h``: six RGB565
``lv_image_dsc_t`` descriptors, one per destination, in menu order.

Keeping the crop tight to the blue tile (no background margin) is deliberate -
the widget rounds the corners, so any surrounding pale background would show up
as a light band along the straight edges.

Usage:
    python tools/makeicons.py <reference.png> [out_size]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pngread import read_png  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Menu order: the order of analyzer_screen_t's home entries.
NAMES = ["test", "result", "system", "maintenance", "power", "about"]


def is_blue(p):
    r, g, b = p
    return b > 140 and b - r > 60 and b - g > 20


def px(rows, x, y):
    o = x * 3
    return rows[y][o], rows[y][o + 1], rows[y][o + 2]


def bands(counts, threshold, minimum):
    out = []
    start = None
    for i, c in enumerate(counts):
        if c > threshold and start is None:
            start = i
        elif c <= threshold and start is not None:
            if i - start >= minimum:
                out.append((start, i - 1))
            start = None
    if start is not None and len(counts) - start >= minimum:
        out.append((start, len(counts) - 1))
    return out


def find_tiles(w, h, rows):
    """Return the six blue tile rectangles in reading order.

    The scan walks the columns, so the result is reassembled across the rows
    before it is returned: TEST RESULT SYSTEM / MAINTENANCE POWER ABOUT.
    """
    col_hits = [0] * w
    for y in range(h):
        for x in range(w):
            if is_blue(px(rows, x, y)):
                col_hits[x] += 1

    # A tile is ~240 px tall in the reference, so a column crossing one has
    # hundreds of blue pixels; text and hairlines never come close.
    tall = max(col_hits) // 4
    cols = bands(col_hits, tall, 40)
    if len(cols) != 3:
        raise SystemExit("expected 3 icon columns, found %d" % len(cols))

    per_column = []
    for (x0, x1) in cols:
        row_hits = [0] * h
        for y in range(h):
            for x in range(x0, x1 + 1):
                if is_blue(px(rows, x, y)):
                    row_hits[y] += 1
        wide = (x1 - x0 + 1) // 4
        rows_b = bands(row_hits, wide, 40)
        if len(rows_b) != 2:
            raise SystemExit("expected 2 icon rows, found %d" % len(rows_b))

        column = []
        for (y0, y1) in rows_b:
            # Tighten to the true blue bounds inside the detected band.
            bx0, bx1, by0, by1 = x1, x0, y1, y0
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if is_blue(px(rows, x, y)):
                        bx0, bx1 = min(bx0, x), max(bx1, x)
                        by0, by1 = min(by0, y), max(by1, y)
            column.append((bx0, by0, bx1, by1))
        per_column.append(column)

    return [per_column[c][r] for r in range(2) for c in range(len(cols))]


def resize(rows, box, out_w, out_h):
    """Box-average the crop in ``box`` down to ``out_w`` x ``out_h`` RGB565.

    Box averaging (rather than dropping pixels) is what keeps the glossy
    highlights on the reference icons from turning into aliased speckle.
    """
    x0, y0, x1, y1 = box
    sw, sh = x1 - x0 + 1, y1 - y0 + 1

    out = []
    for dy in range(out_h):
        sy0 = y0 + (dy * sh) // out_h
        sy1 = y0 + ((dy + 1) * sh) // out_h
        if sy1 <= sy0:
            sy1 = sy0 + 1
        for dx in range(out_w):
            sx0 = x0 + (dx * sw) // out_w
            sx1 = x0 + ((dx + 1) * sw) // out_w
            if sx1 <= sx0:
                sx1 = sx0 + 1

            rs = gs = bs = n = 0
            for y in range(sy0, min(sy1, y0 + sh)):
                for x in range(sx0, min(sx1, x0 + sw)):
                    r, g, b = px(rows, x, y)
                    rs += r
                    gs += g
                    bs += b
                    n += 1
            r, g, b = rs // n, gs // n, bs // n
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out.append(v & 0xFF)
            out.append((v >> 8) & 0xFF)

    return out


def emit(icons, w, h):
    lines = [
        "#ifndef HOME_ICONS_H",
        "#define HOME_ICONS_H",
        "",
        "/*",
        " * The six home menu icons (TEST, RESULT, SYSTEM, MAINTENANCE, POWER,",
        " * ABOUT), cut from the supplied reference artwork by tools/makeicons.py",
        " * and stored as RGB565, %d x %d each." % (w, h),
        " *",
        " * Generated file - do not edit by hand. Each crop is the bare blue tile,",
        " * corner radius and all, with no surrounding background, so it can be",
        " * drawn straight onto the light home background.",
        " *",
        " * Flash: %s bytes per icon, %s for the six."
        % ("{:,}".format(w * h * 2), "{:,}".format(w * h * 2 * len(icons))),
        " */",
        "",
        '#include "lvgl.h"',
        "",
    ]

    for name, data in zip(NAMES, icons):
        lines.append("static const uint8_t home_icon_%s_map[] = {" % name)
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            lines.append("    " + " ".join("0x%02x," % b for b in chunk))
        lines.append("};")
        lines.append("")
        lines.append("static const lv_image_dsc_t home_icon_%s = {" % name)
        lines.append("    .header.magic = LV_IMAGE_HEADER_MAGIC,")
        lines.append("    .header.cf = LV_COLOR_FORMAT_RGB565,")
        lines.append("    .header.flags = 0,")
        lines.append("    .header.w = %d," % w)
        lines.append("    .header.h = %d," % h)
        lines.append("    .header.stride = (%d * 2)," % w)
        lines.append("    .data_size = sizeof(home_icon_%s_map)," % name)
        lines.append("    .data = home_icon_%s_map," % name)
        lines.append("};")
        lines.append("")

    lines.append("#endif /* HOME_ICONS_H */")
    lines.append("")

    path = os.path.join(ROOT, "home_icons.h")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))

    return path


def main():
    ref = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 128

    w, h, rows = read_png(ref)
    print("reference %dx%d" % (w, h))

    tiles = find_tiles(w, h, rows)
    print("%d tiles" % len(tiles))
    for i, t in enumerate(tiles):
        print("  %-12s %s  %dx%d" % (NAMES[i], t, t[2] - t[0] + 1, t[3] - t[1] + 1))

    # Keep the reference tile's own proportions rather than forcing a square:
    # squaring them would stretch the artwork.
    tw = tiles[0][2] - tiles[0][0] + 1
    th = tiles[0][3] - tiles[0][1] + 1
    out_w = width
    out_h = int(round(width * th / float(tw)))
    print("emitting %dx%d per icon" % (out_w, out_h))

    icons = [resize(rows, t, out_w, out_h) for t in tiles]
    path = emit(icons, out_w, out_h)
    print("wrote %s (%s bytes of pixels)"
          % (path, "{:,}".format(sum(len(i) for i in icons))))


if __name__ == "__main__":
    main()
