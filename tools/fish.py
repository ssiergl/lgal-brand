#!/usr/bin/env python3
"""Rebuild the puffer fish of the original as SVG: shapes traced per region, shading fitted
to the original pixels.  Usage: fish.py original.bmp out_fragment.svg debug_dir"""
import os
import re
import struct
import sys
import zlib

import numpy as np
import vtracer
from scipy import ndimage

src, dst, dbg = sys.argv[1:4]
os.makedirs(dbg, exist_ok=True)
rng = np.random.default_rng(1)

# --- load BMP (24 bit) -------------------------------------------------------------------
d = open(src, "rb").read()
off = struct.unpack_from("<I", d, 10)[0]
W, H = struct.unpack_from("<ii", d, 18)
bottom_up = H > 0
H = abs(H)
stride = (W * 3 + 3) & ~3
raw = np.frombuffer(d, np.uint8, count=stride * H, offset=off).reshape(H, stride)[:, :W * 3]
img = raw.reshape(H, W, 3)[:, :, ::-1].astype(np.float32)  # BGR -> RGB
if bottom_up:
    img = img[::-1]
K = W / 1000  # pixels per logo unit
ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
X, Y = (xs + 0.5) / K, (ys + 0.5) / K

# --- region masks (logo units), same as quantize.py ------------------------------------
LINE = [(140, 2000), (300, 760), (315, 660), (350, 612), (400, 564), (450, 541), (550, 522), (600, 500), (2000, 0)]
line_x = np.interp(Y, [p[0] for p in LINE], [p[1] for p in LINE])
near_line = np.abs(X - line_x) < 26
in_fish = ((X - 505) ** 2 + (Y - 330) ** 2 <= 186 ** 2) & (X < line_x)
in_fin_box = (X >= 590) & (X <= 668) & (Y >= 168) & (Y <= 245)
in_side_fin = (X > 500) & (X < 590) & (Y > 280) & (Y < 385)
axis = 698 - 0.151 * (Y - 359)
hw = np.select([Y < 304, Y < 352, Y < 505, Y < 521, Y < 552],
               [34, 53, 32, 32 - (Y - 505) / 16 * 11, 21], 21 - (Y - 552) / 20 * 13)
in_pipette = (Y >= 238) & (Y <= 572) & (np.abs(X - axis) <= hw)

r, g, b = img[..., 0], img[..., 1], img[..., 2]
lum = 0.3 * r + 0.59 * g + 0.11 * b
spread = img.max(-1) - img.min(-1)
dist = lambda c: np.sqrt(((img - np.array(c, np.float32)) ** 2).sum(-1))
warm = b < r - 10  # gold, orange and their dark anti-aliasing (the fish itself is cool)
orange = (r > b + 50) & (r > g) & in_side_fin & ~near_line
navy = dist((13, 38, 59)) < 32
light = (lum > 165) & (spread < 70)

area = ~in_pipette & (in_fish | in_fin_box) & ~(warm & ~orange)
fish = area & ~navy
cls_orange = area & orange
cls_light = area & light & ~orange
cls_body = fish & ~cls_orange & ~cls_light
R_c = np.sqrt((X - 505) ** 2 + (Y - 330) ** 2)
# Light areas: the white rim band outside, belly and highlights inside. Decide per connected
# area (by where most of it lies), so no piece of the belly turns white or the other way round.
light_lab, light_n = ndimage.label(cls_light)
inner_area = np.r_[False, ndimage.mean(R_c <= 150, light_lab, np.arange(1, light_n + 1)) > 0.5][light_lab]
cls_rim = cls_light & ~inner_area
cls_belly = cls_light & inner_area & (Y > 345)
cls_spark = cls_light & inner_area & (Y <= 345)


def dilate(m, rad):
    out = m.copy()
    for dy in range(-rad, rad + 1):
        for dx in range(-rad, rad + 1):
            if dx * dx + dy * dy <= rad * rad:
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def fill_holes(m):
    outside = np.zeros_like(m)
    outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = True
    outside &= ~m
    while True:
        grown = outside.copy()
        grown[1:] |= outside[:-1]
        grown[:-1] |= outside[1:]
        grown[:, 1:] |= outside[:, :-1]
        grown[:, :-1] |= outside[:, 1:]
        grown &= ~m
        if (grown == outside).all():
            return ~outside
        outside = grown


# work in a crop around the fish to keep it fast
r0, r1, c0, c1 = int(150 * K), int(530 * K), int(320 * K), int(700 * K)
crop = lambda m: m[r0:r1, c0:c1]
sil = dilate(fill_holes(crop(fish)), int(5 * K))


def write_png(path, m):
    rgb = np.where(m[..., None], 0, 255).astype(np.uint8).repeat(3, -1)
    rows = b"".join(b"\0" + row.tobytes() for row in rgb)
    ch = lambda t, x: struct.pack(">I", len(x)) + t + x + struct.pack(">I", zlib.crc32(t + x) & 0xffffffff)
    hgt, wid = m.shape
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", wid, hgt, 8, 2, 0, 0, 0)) +
                           ch(b"IDAT", zlib.compress(rows, 6)) + ch(b"IEND", b""))


def fmt(v):
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def smooth(m, rad):
    """Majority filter in a (2 rad + 1)^2 box: removes jagged class edges and specks."""
    if rad == 0:
        return m
    f = np.pad(m.astype(np.float32), rad + 1, mode="edge")
    c = f.cumsum(0).cumsum(1)
    n = 2 * rad + 1
    box = c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]
    return box[: m.shape[0], : m.shape[1]] / (n * n) > 0.5


def trace(name, m, speckle=6, rad=4):
    """Binary trace of a crop mask -> list of path data strings in logo units."""
    png, svg = f"{dbg}/{name}.png", f"{dbg}/{name}.svg"
    m = smooth(smooth(m, rad), rad)
    write_png(png, m)
    vtracer.convert_image_to_svg_py(png, svg, colormode="binary", mode="spline", filter_speckle=speckle,
                                    corner_threshold=60, length_threshold=4.0, splice_threshold=45,
                                    path_precision=2)
    parts = []
    for pm in re.finditer(r'<path d="([^"]+)"[^>]*transform="translate\(([-\d.]+),([-\d.]+)\)"', open(svg).read()):
        tx, ty = float(pm.group(2)) + c0, float(pm.group(3)) + r0
        out, i = [], 0
        for t in re.findall(r"[MCLZ]|-?\d+(?:\.\d+)?", pm.group(1)):
            if t in "MCLZ":
                out.append(t)
                i = 0
            else:
                out.append(fmt((float(t) + (tx if i % 2 == 0 else ty)) / K))
                i += 1
        parts.append(re.sub(r" ?([MCLZ]) ?", r"\1", " ".join(out)))
    return parts


hexc = lambda c: "#%02x%02x%02x" % tuple(int(round(v)) for v in np.clip(c, 0, 255))


def samples(m, n=6000):
    mm = crop(m)
    px, x, y = crop(img)[mm], crop(X)[mm], crop(Y)[mm]
    i = rng.choice(len(x), min(n, len(x)), replace=False)
    return px[i], x[i], y[i]


def linear_gradient(gid, m, stops=7):
    """Linear gradient along the direction of steepest luminance change, stops = binned medians."""
    px, x, y = samples(m, 20000)
    L = px @ np.array([0.3, 0.59, 0.11], np.float32)
    coef, *_ = np.linalg.lstsq(np.stack([np.ones_like(x), x, y], 1), L, rcond=None)
    v = coef[1:] / np.hypot(*coef[1:])
    t = x * v[0] + y * v[1]
    lo, hi = np.percentile(t, 1), np.percentile(t, 99)
    cx, cy = x.mean(), y.mean()
    tc = cx * v[0] + cy * v[1]
    p1 = (cx + (lo - tc) * v[0], cy + (lo - tc) * v[1])
    p2 = (cx + (hi - tc) * v[0], cy + (hi - tc) * v[1])
    edges = np.linspace(lo, hi, stops + 1)
    st = []
    for i in range(stops):
        sel = (t >= edges[i]) & (t <= edges[i + 1])
        if sel.sum() >= 20:
            st.append((((edges[i] + edges[i + 1]) / 2 - lo) / (hi - lo), hexc(np.median(px[sel], 0))))
    s = "".join(f'<stop offset="{o:.2f}" stop-color="{c}"/>' for o, c in st)
    return (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{p1[0]:.0f}" y1="{p1[1]:.0f}" '
            f'x2="{p2[0]:.0f}" y2="{p2[1]:.0f}">{s}</linearGradient>')


# --- body shading model ------------------------------------------------------------------
# base: linear gradient p1 (c0) -> p2 (c1); overlay A: rim light, radial around (ax, ay), alpha 0 at
# ra*k .. 1 at ra; overlay B: eye ring, radial around the eye, alpha 0 at 0.5 rb -> 1 at 0.8 rb -> 0 at rb.
EYE = (454.7, 293.6)  # pupil centre (measured)
PUPIL_R, DISC_R = 22.5, 35.5


def ramp(t):
    return np.clip(t, 0, 1)


def alphas(p, x, y):
    ang, ax, ay, ra, k, rb = p
    dx, dy = np.cos(ang), np.sin(ang)
    t = x * dx + y * dy
    lo, hi = (np.array([350, 200]) @ (dx, dy)), 0
    da = np.hypot(x - ax, y - ay)
    aA = ramp((da - k * ra) / ((1 - k) * ra))
    return t, aA


def design(p, x, y, tr):
    t, aA = alphas(p, x, y)
    tn = np.clip((t - tr[0]) / (tr[1] - tr[0]), 0, 1)
    # colour = (c0 (1-tn) + c1 tn)(1-aA) + cA aA  -> linear in c0, c1, cA
    return np.stack([(1 - tn) * (1 - aA), tn * (1 - aA), aA], 1)


def solve(p, px, x, y):
    t, _ = alphas(p, x, y)
    tr = (t.min(), t.max())
    M = design(p, x, y, tr)
    C, *_ = np.linalg.lstsq(M, px, rcond=None)
    C = np.clip(C, 0, 255)
    err = ((M @ C - px) ** 2).mean()
    return err, C, tr


def fit_body():
    px, x, y = samples(cls_body & ~near_line, 5000)
    best = None
    for it in range(4000):
        if best is None or it < 1500:
            p = (rng.uniform(0, 2 * np.pi), rng.uniform(420, 620), rng.uniform(250, 420),
                 rng.uniform(120, 260), rng.uniform(0.5, 0.95), rng.uniform(30, 70))
        else:
            p = tuple(v + rng.normal(0, s) for v, s in zip(best[1], (0.1, 8, 8, 8, 0.03, 3)))
            p = (p[0], p[1], p[2], max(p[3], 60), min(max(p[4], 0.2), 0.97), max(p[5], 25))
        err, C, tr = solve(p, px, x, y)
        if best is None or err < best[0]:
            best = (err, p, C, tr)
    return best


def body_defs():
    global BODY_FIT
    err, p, C, (tlo, thi) = BODY_FIT = fit_body()
    ang, ax, ay, ra, k, rb = p
    dx, dy = np.cos(ang), np.sin(ang)
    cx, cy = 505.0, 300.0
    tc = cx * dx + cy * dy
    p1 = (cx + (tlo - tc) * dx, cy + (tlo - tc) * dy)
    p2 = (cx + (thi - tc) * dx, cy + (thi - tc) * dy)
    print(f"body fit rms {np.sqrt(err):.1f}  p={tuple(round(float(v), 2) for v in p)}  "
          f"colours {[hexc(c) for c in C]}", file=sys.stderr)
    c0, c1, cA = (hexc(c) for c in C)
    return [
        f'<linearGradient id="f-body" gradientUnits="userSpaceOnUse" x1="{p1[0]:.0f}" y1="{p1[1]:.0f}" '
        f'x2="{p2[0]:.0f}" y2="{p2[1]:.0f}"><stop offset="0" stop-color="{c0}"/>'
        f'<stop offset="1" stop-color="{c1}"/></linearGradient>',
        f'<radialGradient id="f-rim" gradientUnits="userSpaceOnUse" cx="{ax:.0f}" cy="{ay:.0f}" r="{ra:.0f}">'
        f'<stop offset="{k:.2f}" stop-color="{cA}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{cA}"/></radialGradient>',
    ]


def highlights():
    """Body pixels clearly lighter than the shading model: the spots and the ring around the eye."""
    err, p, C, tr = BODY_FIT
    m = crop(cls_body)
    x, y, px = crop(X)[m], crop(Y)[m], crop(img)[m]
    model = design(p, x, y, tr) @ C
    w = np.array([0.3, 0.59, 0.11], np.float32)
    res = px @ w - model @ w
    hi = np.zeros_like(m)
    de = np.hypot(crop(X) - EYE[0], crop(Y) - EYE[1])
    hi[m] = (res > np.where(de[m] <= 52, 8, 18)) & (y < 335)
    body_lab, _ = ndimage.label(m)
    main = body_lab == np.argmax(np.bincount(body_lab.ravel())[1:]) + 1  # not on the lips
    ring, spots = hi & (de <= 52), hi & (de > 52) & main
    spot_c = hexc(np.median(crop(img)[spots], 0))
    print(f"spots {spot_c}", file=sys.stderr)
    return ring, spots, spot_c


def crop_gradient(gid, m_crop, stops=5):
    full = np.zeros(img.shape[:2], bool)
    full[r0:r1, c0:c1] = m_crop
    return linear_gradient(gid, full, stops)


defs = body_defs() + [linear_gradient("f-belly", cls_belly), linear_gradient("f-fin", cls_orange)]
ring, spots, spot_c = highlights()
dEye = np.hypot(X - EYE[0], Y - EYE[1])
defs.append(linear_gradient("f-eye", (dEye > PUPIL_R + 2) & (dEye < DISC_R - 1), 5))
eye_disc = f'M{EYE[0] - DISC_R:.1f} {EYE[1]:.1f}a{DISC_R} {DISC_R} 0 1 0 {2 * DISC_R} 0a{DISC_R} {DISC_R} 0 1 0 {-2 * DISC_R} 0Z'
pupil = f'M{EYE[0] - PUPIL_R:.1f} {EYE[1]:.1f}a{PUPIL_R} {PUPIL_R} 0 1 0 {2 * PUPIL_R} 0a{PUPIL_R} {PUPIL_R} 0 1 0 {-2 * PUPIL_R} 0Z'
body = trace("body", crop(cls_body))
layers = [
    ("#0d263b", trace("sil", sil, 20)),
    ("url(#f-body)", body),
    ("url(#f-rim)", body),
    ("url(#f-eye)", [eye_disc]),
    ("#0d263b", [pupil]),
    (spot_c, trace("spots", spots, 8, 3)),
    ("url(#f-belly)", trace("belly", crop(cls_belly))),
    ("#fbfbf9", trace("rim", crop(cls_rim))),
    ("#fbfbf9", trace("spark", crop(cls_spark), 2, 2)),
    ("url(#f-fin)", trace("fin", crop(cls_orange))),
]
with open(dst, "w") as f:
    f.write("<defs>" + "".join(defs) + "</defs>\n<g id=\"fish\">\n")
    for fill, parts in layers:
        f.write(f'<g fill="{fill}">' + "".join(f'<path d="{p}"/>' for p in parts) + "</g>\n")
    f.write("</g>\n")
