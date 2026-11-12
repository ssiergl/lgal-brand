"""Snap traced paths to the palette, drop navy, scale to 1000 units, split outer ring vs inner.
Writes JSON: [{"c": colour name, "outer": bool, "d": path data}]"""
import json
import math
import re
import sys

PAL = {"navy": (0x0d, 0x26, 0x3b), "teal": (0x35, 0x95, 0xa2),
       "gold": (0xd6, 0x9f, 0x31), "white": (0xfb, 0xfb, 0xf9)}
CX, CY, R_SPLIT = 507, 488, 368  # text and outer arcs lie outside R_SPLIT, the gold circle inside


def nearest(hexc):
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    return min(PAL, key=lambda k: sum((a - c) ** 2 for a, c in zip((r, g, b), PAL[k])))


def fmt(v):
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def convert(d, tx, ty):
    """vtracer emits absolute M/C/L/Z with x y pairs; returns (path data, list of points)."""
    out, pts, i, x = [], [], 0, 0.0
    for t in re.findall(r"[MCLZ]|-?\d+(?:\.\d+)?", d):
        if t in "MCLZ":
            out.append(t)
            i = 0
            continue
        v = (float(t) + (tx if i % 2 == 0 else ty)) * 0.5
        if i % 2 == 0:
            x = v
        else:
            pts.append((x, v))
        out.append(fmt(v))
        i += 1
    return re.sub(r" ?([MCLZ]) ?", r"\1", " ".join(out)), pts


def main(src, dst):
    svg = open(src).read()
    res = []
    for m in re.finditer(r'<path d="([^"]+)" fill="(#[0-9A-Fa-f]{6})"[^>]*?transform="translate\(([-\d.]+),([-\d.]+)\)"', svg):
        c = nearest(m.group(2))
        if c == "navy":
            continue
        d, pts = convert(m.group(1), float(m.group(3)), float(m.group(4)))
        rmin = min(math.hypot(x - CX, y - CY) for x, y in pts)
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        res.append({"c": c, "outer": rmin > R_SPLIT, "d": d, "bb": [min(xs), min(ys), max(xs), max(ys)]})
    json.dump(res, open(dst, "w"))
    print({(c, o): sum(1 for p in res if p["c"] == c and p["outer"] == o)
           for c in ("teal", "gold", "white") for o in (False, True)})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
