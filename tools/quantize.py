#!/usr/bin/env python3
"""original.bmp -> flat.png: 4 palette colours, fish blanked, pipette kept (navy).
Coordinates in logo units (1000 = image width)."""
import math, struct, sys, zlib

src, dst = sys.argv[1], sys.argv[2]
PAL = {"navy": (13, 38, 59), "teal": (53, 149, 162), "gold": (214, 159, 49), "white": (251, 251, 249)}
NAMES = list(PAL)
data = open(src, "rb").read()
off = struct.unpack_from("<I", data, 10)[0]
w, h = struct.unpack_from("<ii", data, 18)
bpp = struct.unpack_from("<H", data, 28)[0]
bottom_up = h > 0
h = abs(h)
stride = (w * bpp // 8 + 3) & ~3
S = w / 1000

# gold line that bounds the fish on its lower right (logo units): x of the line at y
LINE = [(140, 2000), (300, 760), (315, 660), (350, 612), (400, 564), (450, 541), (550, 522), (600, 500), (2000, 0)]
def line_x(y):
    for (y0, x0), (y1, x1) in zip(LINE, LINE[1:]):
        if y0 <= y <= y1:
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return 0

def in_fin_box(x, y):
    return 590 <= x <= 668 and 168 <= y <= 245

def in_fish(x, y):
    if (x - 505) ** 2 + (y - 330) ** 2 > 186 ** 2:
        return False
    return x < line_x(y)

def near_line(x, y):
    return abs(x - line_x(y)) < 26

# pipette (measured): axis x = 698 - 0.151 * (y - 359); half widths by height
def pipette_axis(y):
    return 698 - 0.151 * (y - 359)

def in_pipette(x, y):
    if y < 238 or y > 572:
        return False
    if y < 304: hw = 34
    elif y < 352: hw = 53
    elif y < 505: hw = 32
    elif y < 521: hw = 32 - (y - 505) / 16 * 11
    elif y < 552: hw = 21
    else: hw = 21 - (y - 552) / 20 * 13
    return abs(x - pipette_axis(y)) <= hw

out = bytearray()
counts = dict.fromkeys(NAMES, 0)
for row in range(h):
    r_src = (h - 1 - row) if bottom_up else row
    base = off + r_src * stride
    out.append(0)  # PNG filter type
    y = (row + 0.5) / S
    for col in range(w):
        b, g, r = data[base + col * 3], data[base + col * 3 + 1], data[base + col * 3 + 2]
        x = (col + 0.5) / S
        best = min(NAMES, key=lambda n: (r - PAL[n][0]) ** 2 + (g - PAL[n][1]) ** 2 + (b - PAL[n][2]) ** 2)
        if not in_pipette(x, y) and ((in_fish(x, y) and (best != "gold" or not near_line(x, y)))
                                     or (in_fin_box(x, y) and best != "gold")):
            best = "navy"
        counts[best] += 1
        out += bytes(PAL[best])

def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
      chunk(b"IDAT", zlib.compress(bytes(out), 6)) + chunk(b"IEND", b"")
open(dst, "wb").write(png)
print(w, h, {k: round(v / (w * h) * 100, 1) for k, v in counts.items()})
