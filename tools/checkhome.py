"""checkhome.py - verify the home menu render against the reference layout.

The home screen is only the six illustrated keys and their names, so the things
worth checking are the ones a user would notice: exactly six keys, the right
size and grid, a readable name under each one inside its own cell, the
hairlines, and nothing else on the panel and nothing clipped at its edges.

Usage:
    python tools/checkhome.py shots/home.bmp
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bmp2png import read_bmp  # noqa: E402

NAMES = ["TEST", "RESULT", "SYSTEM", "MAINTENANCE", "POWER", "ABOUT"]

PANEL_W, PANEL_H = 800, 480
EXPECT_W, EXPECT_H = 130, 121


def px(rows, x, y):
    o = x * 3
    return rows[y][o], rows[y][o + 1], rows[y][o + 2]


def is_key_blue(p):
    """The illustrated keys' blue, which is far more saturated than anything
    else on the panel."""
    r, g, b = p
    return b > 150 and b - r > 80 and b - g > 40


def is_ink(p):
    """The navy caption."""
    r, g, b = p
    return r < 130 and g < 130 and b < 175


def runs(flags, minimum):
    out = []
    start = None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= minimum:
                out.append((start, i - 1))
            start = None
    if start is not None and len(flags) - start >= minimum:
        out.append((start, len(flags) - 1))
    return out


def key_boxes(rows):
    cols = [0] * PANEL_W
    for y in range(PANEL_H):
        for x in range(PANEL_W):
            if is_key_blue(px(rows, x, y)):
                cols[x] += 1

    boxes = []
    for (x0, x1) in runs([c > 30 for c in cols], 40):
        row_hits = [0] * PANEL_H
        for y in range(PANEL_H):
            for x in range(x0, x1 + 1):
                if is_key_blue(px(rows, x, y)):
                    row_hits[y] += 1

        per_row = runs([c > 30 for c in row_hits], 40)
        for (y0, y1) in per_row:
            # tighten to the true blue bounds
            bx0, bx1, by0, by1 = x1, x0, y1, y0
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if is_key_blue(px(rows, x, y)):
                        bx0, bx1 = min(bx0, x), max(bx1, x)
                        by0, by1 = min(by0, y), max(by1, y)
            boxes.append((bx0, by0, bx1, by1))

    # column-major scan -> reading order
    per_column = [boxes[i:i + 2] for i in range(0, len(boxes), 2)]
    ordered = []
    for r in range(2):
        for col in per_column:
            if r < len(col):
                ordered.append(col[r])
    return ordered


def main(path):
    w, h, rows = read_bmp(path)
    print("%s  %dx%d" % (path, w, h))

    problems = []

    keys = key_boxes(rows)
    print("keys: %d" % len(keys))
    if len(keys) != 6:
        problems.append("expected 6 keys, found %d" % len(keys))

    cells_w = (w - 2 * 36) / 3.0
    cells_h = (h - 2 * 38) / 2.0

    labels = []
    for i, (x0, y0, x1, y1) in enumerate(keys):
        gw, gh = x1 - x0 + 1, y1 - y0 + 1

        band = range(y1 + 1, min(h, y1 + 60))
        pts = [(x, y) for y in band
               for x in range(max(0, x0 - 60), min(w, x1 + 61))
               if is_ink(px(rows, x, y))]

        if pts:
            lx0 = min(p[0] for p in pts)
            lx1 = max(p[0] for p in pts)
            ly0 = min(p[1] for p in pts)
            ly1 = max(p[1] for p in pts)
            labels.append((lx0, ly0, lx1, ly1))
            label = "label=(%d,%d)-(%d,%d) %dx%d" % (
                lx0, ly0, lx1, ly1, lx1 - lx0 + 1, ly1 - ly0 + 1)
        else:
            labels.append(None)
            label = "label=MISSING"

        print("  %-12s key=(%d,%d)-(%d,%d) %dx%d  %s"
              % (NAMES[i], x0, y0, x1, y1, gw, gh, label))

        if abs(gw - EXPECT_W) > 8 or abs(gh - EXPECT_H) > 8:
            problems.append("key %s is %dx%d, expected about %dx%d"
                            % (NAMES[i], gw, gh, EXPECT_W, EXPECT_H))
        if abs((x0 + x1) / 2.0 - (36 + cells_w * (i % 3) + cells_w / 2)) > 12:
            problems.append("key %s is not centred in its column" % NAMES[i])
        if labels[i] is None:
            problems.append("key %s has no name under it" % NAMES[i])
        else:
            lx0, ly0, lx1, ly1 = labels[i]
            if ly0 <= y1:
                problems.append("%s label overlaps its key" % NAMES[i])
            if (ly1 - ly0 + 1) > 28:
                problems.append("%s label is more than one line (%d px tall)"
                                % (NAMES[i], ly1 - ly0 + 1))
            left = x0 - 36
            right = x0 + cells_w - 36
            if lx0 < left or lx1 > right:
                problems.append("%s label spills out of its cell" % NAMES[i])
            if ly1 >= h - 2:
                problems.append("%s label runs off the panel" % NAMES[i])

    # --- nothing but the keys and their names ---
    # Any ink or saturated colour outside the key/label bounding boxes, the
    # hairlines, and the panel margin is extra content.
    key_marks = 0
    for y in range(h):
        for x in range(w):
            if is_key_blue(px(rows, x, y)):
                key_marks += 1
    print("key pixels: %d" % key_marks)

    # --- hairlines ---
    bg = px(rows, 4, h // 2)

    def mark(x, y):
        r, g, b = px(rows, x, y)
        return (abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])) > 25

    top = min(y0 for _, y0, _, _ in keys)
    bottom = max(y1 for _, _, _, y1 in keys)

    vert = []
    for x in range(w):
        column = [mark(x, y) for y in range(top, bottom + 1)]
        # a hairline is one unbroken run down the menu area
        if any(e - s >= 250 for (s, e) in runs(column, 250)):
            vert.append(x)
    horiz = []
    for y in range(h):
        if runs([mark(x, y) for x in range(w)], 600):
            horiz.append(y)

    print("vertical hairlines at x=%s" % vert)
    print("horizontal hairlines at y=%s" % horiz)

    if len(vert) != 2:
        problems.append("expected 2 vertical hairlines, found %d" % len(vert))
    if len(horiz) != 1:
        problems.append("expected 1 horizontal hairline, found %d" % len(horiz))
    else:
        if abs(horiz[0] - h / 2.0) > 6:
            problems.append("the horizontal hairline is not at mid-height")

    # --- the menu fills the panel's middle: the outer margins must be clear ---
    for x in range(0, 20):
        for y in range(h):
            if is_key_blue(px(rows, x, y)) or is_ink(px(rows, x, y)):
                problems.append("content in the left margin at x=%d" % x)
                break
    for y in list(range(0, 20)) + list(range(h - 20, h)):
        for x in range(w):
            if is_key_blue(px(rows, x, y)) or is_ink(px(rows, x, y)):
                problems.append("content in the top/bottom margin at y=%d" % y)
                break

    # --- no header / status strip: the band above the keys holds only rules ---
    above = 0
    for y in range(0, top - 2):
        for x in range(w):
            if is_key_blue(px(rows, x, y)) or is_ink(px(rows, x, y)):
                above += 1
    print("non-rule marks above the keys: %d" % above)
    if above:
        problems.append("there is content above the keys (%d px)" % above)

    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
    else:
        print("verdict: PASS - six keys, names in-cell, hairlines, "
              "no extra content, nothing clipped")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "shots/home.bmp")
