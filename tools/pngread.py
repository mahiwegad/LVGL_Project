"""pngread.py - a minimal stdlib PNG reader.

Pillow is not installed here, so the reference artwork (a PNG) cannot be opened
with the usual tooling. This decodes the subset a screenshot/render uses:
8-bit RGB or RGBA, non-interlaced, with the five standard scanline filters.

Usage:
    from pngread import read_png
    w, h, rows = read_png("shot.png")     # rows are top-down RGB bytes
"""

import struct
import zlib


def _unfilter(data, width, height, bpp):
    stride = width * bpp
    out = bytearray(height * stride)

    pos = 0
    prev = bytearray(stride)

    for y in range(height):
        ftype = data[pos]
        pos += 1
        line = bytearray(data[pos:pos + stride])
        pos += stride

        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif ftype != 0:
            raise ValueError("unsupported PNG filter %d" % ftype)

        out[y * stride:(y + 1) * stride] = line
        prev = line

    return out


def read_png(path):
    """Return (width, height, rows) with rows as top-down RGB bytes."""
    with open(path, "rb") as handle:
        data = handle.read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s is not a PNG" % path)

    pos = 8
    idat = bytearray()
    width = height = depth = color = None

    while pos < len(data):
        length = struct.unpack_from(">I", data, pos)[0]
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if tag == b"IHDR":
            width, height, depth, color, comp, filt, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if depth != 8 or interlace != 0 or color not in (2, 6):
                raise ValueError(
                    "unsupported PNG: depth=%d color=%d interlace=%d"
                    % (depth, color, interlace)
                )
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break

    channels = 3 if color == 2 else 4
    raw = zlib.decompress(bytes(idat))
    flat = _unfilter(raw, width, height, channels)

    if channels == 3:
        return width, height, [
            bytes(flat[y * width * 3:(y + 1) * width * 3]) for y in range(height)
        ]

    rows = []
    for y in range(height):
        base = y * width * 4
        row = bytearray(width * 3)
        for x in range(width):
            o = base + x * 4
            row[x * 3:x * 3 + 3] = flat[o:o + 3]
        rows.append(bytes(row))

    return width, height, rows
