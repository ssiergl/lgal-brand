#!/usr/bin/env python3
"""Gold lines of the logo as constant-width strokes on smooth centre lines, measured from the original.

Every gold line is one stroke of width W on a fitted centre line: the ring is an exact circle, the two
verticals of the L are straight lines, the other lines are cubic Bezier curves. Ends are cut along the
measured end of the original line (clip paths); the two curled tips of the hook use the original's
outline. Writes an SVG fragment (<defs> with the clip paths and <g id="gold">) and debug/diff.png
(grey = both, red = original only, green = new only).

Usage: strokes.py gold-mask.npy goldness.npy out-fragment.svg debug_dir"""
import re
import struct
import sys
import zlib

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage.measure import find_contours, points_in_poly

import bezfit
import cl

mask_p, good_p, out_p, dbg = sys.argv[1:5]
cl.load(mask_p)
G = np.load(good_p)
cl.soft = ndimage.gaussian_filter(G, 0.7)
K = 2
CX, CY, R = 510.9, 488.5, 352.85   # ring centre line (fit of both edges)
W = 20.4                            # one width for every gold line
h = W / 2
XA, XB = 270.4, 226.9               # the two straight verticals of the L
EXT = 2 * W

_cs = [np.c_[(c[:, 1] + 0.5) / K, (c[:, 0] + 0.5) / K] for c in find_contours(cl.soft, 0.5)]
EDGE = np.concatenate(_cs)
EDGE_DIR = np.concatenate([np.gradient(ndimage.gaussian_filter1d(c, 2, axis=0, mode="nearest"), axis=0) for c in _cs])
EDGE_DIR /= np.maximum(np.hypot(*EDGE_DIR.T), 1e-9)[:, None]
LAB, _ = ndimage.label(cl.soft > 0.5, np.ones((3, 3)))
LAB = ndimage.grey_dilation(LAB, size=5)
EDGE_LAB = LAB[np.clip((EDGE[:, 1] * K).astype(int), 0, 1999), np.clip((EDGE[:, 0] * K).astype(int), 0, 1999)]


def label_at(p):
    return LAB[int(p[1] * K), int(p[0] * K)]


def unit(v):
    return v / np.hypot(*v)


class Frame:
    """coordinates along a straight or circular continuation of a centre line: s along, q to the left normal"""

    def __init__(self, p, t, rho=None):
        self.p, self.t = np.asarray(p, float), unit(np.asarray(t, float))
        self.n = np.array([-self.t[1], self.t[0]])
        self.rho = rho
        if rho is not None:
            self.c = self.p + self.n * rho

    def to(self, x):
        x = np.atleast_2d(x)
        if self.rho is None:
            d = x - self.p
            return d @ self.t, d @ self.n
        v = x - self.c
        r = np.hypot(*v.T)
        ref = -self.n if self.rho > 0 else self.n
        q = self.rho - r if self.rho > 0 else self.rho + r
        th = np.arctan2(ref[0] * v[:, 1] - ref[1] * v[:, 0], v @ ref)
        return th * self.rho, q

    def back(self, s, q):
        s, q = np.broadcast_arrays(np.asarray(s, float), np.asarray(q, float))
        if self.rho is None:
            return self.p + s[..., None] * self.t + q[..., None] * self.n
        th = s / self.rho
        b = -self.n
        rot = np.stack([b[0] * np.cos(th) - b[1] * np.sin(th), b[0] * np.sin(th) + b[1] * np.cos(th)], -1)
        return self.c + rot * (self.rho - q)[..., None]

    def svg_to(self, s, inward=False):
        """path command running the continuation from s = 0 to s (or back from s to 0 when inward)"""
        end = self.p if inward else self.back(s, 0)
        if self.rho is None:
            return f"L{P(end)}"
        sweep = (self.rho > 0) != inward
        return f"A{fmt(abs(self.rho))} {fmt(abs(self.rho))} 0 0 {int(sweep)} {P(end)}"


def end_frame(pts):
    """frame at pts[0], pointing away from the line, curvature from the first 15 units"""
    q = pts[:51]
    t = unit(q[0] - q[6])
    A = np.c_[2 * q, np.ones(len(q))]
    sol, *_ = np.linalg.lstsq(A, (q ** 2).sum(1), rcond=None)
    cc, rr = sol[:2], np.sqrt(sol[2] + sol[:2] @ sol[:2])
    n = np.array([-t[1], t[0]])
    rho = None if rr > 1500 else float(np.sign((cc - q[0]) @ n) * rr)
    return Frame(q[0], t, rho)


def centre(a, b, sigma=4, bends=False):
    """refined, smoothed centre line between two points (units), only where the stroke has full width"""
    r, w = cl.refine(cl.skel_path(a, b), step=0.5)
    med = np.nanmedian(w)
    good = ~np.isnan(r[:, 0]) & (np.abs(w - med) < 0.6)
    i0, i1 = np.nonzero(good)[0][[0, -1]]
    if bends:  # where the normals cross in a tight bend, the skeleton itself is the better centre
        r = np.where(good[:, None], r, cl.last_base)[i0:i1 + 1]
    else:
        r = r[good]
    seg = np.hypot(*np.diff(r, axis=0).T)
    r = r[np.r_[True, seg > 0.05]]
    seg = np.hypot(*np.diff(r, axis=0).T)
    sl = np.r_[0, np.cumsum(seg)]
    s = np.linspace(0, sl[-1], int(sl[-1] / 0.5) + 1)
    r = np.c_[np.interp(s, sl, r[:, 0]), np.interp(s, sl, r[:, 1])]
    r = ndimage.gaussian_filter1d(r, sigma, axis=0, mode="nearest")[sigma + 6:-sigma - 6]
    return trim_hooks(r)


def trim_hooks(r, tol=2.5):
    """drop end pieces that bend away from the course of the line (the end cap pulls the centre aside)"""
    for _ in range(2):
        hd = np.unwrap(np.arctan2(*np.diff(r, axis=0).T[::-1]))
        i = np.arange(len(hd))
        fit = (i >= 12) & (i < 60)
        c = np.polyfit(i[fit], hd[fit], 1)
        bad = np.abs(np.degrees(hd - np.polyval(c, i))) > tol
        cut = int(np.max(np.nonzero(bad[:12])[0]) + 2) if bad[:12].any() else 0
        if cut:
            print(f"    trimmed {cut * 0.5:.1f} units off a bent end")
        r = r[cut:][::-1]
    return r


def fit_cut(s, q, name):
    """end outline as s(q): a straight cut, or a parabola when the end is clearly curved"""
    c = np.polyfit(q, s, 1)
    kind, sd = "straight", (s - np.polyval(c, q)).std()
    if sd > 0.9:
        c2 = np.polyfit(q, s, 2)
        sd2 = (s - np.polyval(c2, q)).std()
        if sd2 < 0.6 * sd:
            c, kind, sd = c2, "curved", sd2
    print(f"  end {name}: {len(s)} points, {kind}, residual sd {sd:.2f}")
    return lambda qq: np.polyval(c, qq)


def measure_end(fr, name, span=2.6 * W, lab=None, ring=False):
    """outline of the end beyond the frame origin -> clip polygon (world) and the needed extension length"""
    s, q = fr.to(EDGE)
    s1, q1 = fr.to(EDGE + 0.5 * EDGE_DIR)
    steep = np.abs(q1 - q) / 0.5 > np.sin(np.radians(10))
    same = EDGE_LAB == (label_at(fr.p) if lab is None else lab)
    qc = 0.0
    if ring:  # the drawn ring is not perfectly round: centre of the band where the end starts
        band = (s > -40) & (s < -2) & (np.abs(q) < h + 5) & same
        qc = (q[band & (q > 0)].mean() + q[band & (q < 0)].mean()) / 2
    sel = (s > -1) & (s < span) & (np.abs(q - qc) < h - 1) & steep & same
    f = fit_cut(s[sel], q[sel] - qc, name)
    qs = np.linspace(-h - 6, h + 6, 41)
    sc = f(qs)
    smax = sc.max()
    out = np.linspace(smax, smax + 2 * W, 10)
    poly = np.r_[fr.back(sc, qs), fr.back(out, h + 6), fr.back(out[::-1], -h - 6)]
    return poly, smax + W


def oriented(pts, sign):
    pts = np.asarray(pts, float)
    a = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    return pts if np.sign(a) == sign else pts[::-1]


_outline = {}


def outline(lab):
    """smoothed outline of one gold part of the original (for free-form tips only)"""
    if lab not in _outline:
        from skimage.measure import approximate_polygon
        m = ndimage.gaussian_filter(((cl.soft > 0.5) & (LAB == lab)).astype(float), 1.0)
        c = max(find_contours(m, 0.5), key=len)
        c = np.c_[(c[:, 1] + 0.5) / K, (c[:, 0] + 0.5) / K]
        _outline[lab] = approximate_polygon(c, 0.04)[:-1]
    return _outline[lab]


def traced_end(fr, name):
    """tip taken from the original's outline: a box over the end (hole) plus the outline (kept)"""
    lab = label_at(fr.p)
    o = outline(lab)
    s, q = fr.to(o)
    near = (s > 0) & (s < 3 * W) & (np.abs(q) < h + 3)
    smax = s[near].max()
    out = np.linspace(-0.5, smax + 2 * W, 16)
    box = np.r_[fr.back(out, h + 8), fr.back(out[::-1], -h - 8)]
    print(f"  end {name}: traced, reaches {smax:.1f} beyond the last full-width point")
    return box, smax + W, lab


def circ_pt(a):
    a = np.radians(a)
    return np.array([CX + R * np.cos(a), CY + R * np.sin(a)])


def fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def P(p):
    return f"{fmt(p[0])} {fmt(p[1])}"


def curve_d(beziers):
    return "".join(f"C{P(b[1])} {P(b[2])} {P(b[3])}" for b in beziers)


def ring_frame(a0, direction):
    p = circ_pt(a0)
    a = np.radians(a0)
    t = direction * np.array([-np.sin(a), np.cos(a)])
    n = np.array([-t[1], t[0]])
    return Frame(p, t, float(np.sign((np.array([CX, CY]) - p) @ n) * R))


# ---- measure ------------------------------------------------------------------------------------------------
print("ring tips")
fr_top = ring_frame(320, +1)
clip_top, ext_top = measure_end(fr_top, "ring top right", span=90, ring=True)
fr_bot = ring_frame(40, -1)
clip_bot, ext_bot = measure_end(fr_bot, "ring bottom right", span=90, ring=True)

print("A (inner vertical)")
a_end_y = max(p[1] for p in centre((XA, 300), (XA, 545)))
fr_a = Frame((XA, a_end_y - 8), (0, 1))
clip_a, ext_a = measure_end(fr_a, "A bottom")

print("B (L stroke, wave and S)")
wave = centre((240, 568), (634, 330))
w0 = wave[(wave[:, 0] > 246) & (wave[:, 0] < 270)]
ang = np.polyfit(w0[:, 0], w0[:, 1], 1)
corner = np.array([XB, np.polyval(ang, XB)])
print(f"  corner {np.round(corner, 2)}, start slope {np.degrees(np.arctan(ang[0])):.1f} deg")
wave = wave[wave[:, 0] > 246]
fr_s = end_frame(wave[::-1])
clip_s, ext_s = measure_end(fr_s, "S top")
wave_bz = bezfit.fit(wave, 0.12, t1=unit(np.array([1.0, ang[0]])))

print("C (hook)")
hook = centre((762, 316), (743, 374), sigma=8, bends=True)  # the U bend needs a radius above the half width
fr_c1, fr_c2 = end_frame(hook), end_frame(hook[::-1])
clip_c1, ext_c1, lab_c = traced_end(fr_c1, "hook start")
clip_c2, ext_c2, _ = traced_end(fr_c2, "hook end")
hook_bz = bezfit.fit(hook, 0.12)


def min_radius(bz):
    out = []
    for b in bz:
        t = np.linspace(0, 1, 200)
        d1, d2 = bezfit._d1(b, t), bezfit._d2(b, t)
        k = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.hypot(*d1.T) ** 3
        out.append(1 / k.max())
    return min(out)


print(f"  tightest bend: radius {min_radius(hook_bz):.1f} (half width {h:.1f})")

print("V (lower wave)")
up = centre((542, 666), (752, 692))
lo = centre((710, 716), (444, 697))
fr_v1, fr_v2 = end_frame(up), end_frame(lo[::-1])
clip_v1, ext_v1 = measure_end(fr_v1, "V upper start")
clip_v2, ext_v2 = measure_end(fr_v2, "V lower end")
lv = label_at(up[len(up) // 2])
cv = max(find_contours(ndimage.gaussian_filter(((cl.soft > 0.5) & (LAB == lv)).astype(float), 0.7), 0.5), key=len)
cv = np.c_[(cv[:, 1] + 0.5) / K, (cv[:, 0] + 0.5) / K][:-1]
kk = 8
va, vb = cv - np.roll(cv, kk, 0), np.roll(cv, -kk, 0) - cv
turn = np.degrees(np.arctan2(va[:, 0] * vb[:, 1] - va[:, 1] * vb[:, 0], (va * vb).sum(1)))
area = 0.5 * np.sum(cv[:, 0] * np.roll(cv[:, 1], -1) - np.roll(cv[:, 0], -1) * cv[:, 1])
turn *= np.sign(area)  # positive = convex
apex_o, notch = cv[np.argmax(turn)], cv[np.argmin(turn)]
# miter geometry: the vertex sits halfway between the outer tip and the inner notch, the arms leave it
# symmetrically to the tip-notch axis, at the angle that puts the tip exactly at the original's tip
apex = (apex_o + notch) / 2
bis = unit(apex_o - notch)
phi = np.arcsin(min(h / (np.hypot(*(apex_o - notch)) / 2), 1))
rot = lambda v, a: np.array([v[0] * np.cos(a) - v[1] * np.sin(a), v[0] * np.sin(a) + v[1] * np.cos(a)])
du, dl = rot(-bis, phi), rot(-bis, -phi)
if du @ unit(up[-20] - apex) < dl @ unit(up[-20] - apex):
    du, dl = dl, du
print(f"  tip {np.round(apex_o, 2)}, notch {np.round(notch, 2)}, vertex {np.round(apex, 2)}, "
      f"opening {2 * np.degrees(phi):.1f} deg")
FREE = 50  # near the vertex the centre lines are unreliable: one smooth curve into the miter instead


def hermite(p0, t0, p1, t1):
    """smooth bridge p0 -> p1 leaving p0 along t0 and arriving at p1 along t1 (unit vectors), every 0.5 units"""
    L = np.hypot(*(p1 - p0))
    u = np.linspace(0, 1, max(int(L / 0.5), 2))[:, None]
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return h00 * p0 + h10 * L * t0 + h01 * p1 + h11 * L * t1


up = up[np.hypot(*(up - apex).T) > FREE]
lo = lo[np.hypot(*(lo - apex).T) > FREE]
up = np.r_[up, hermite(up[-1], unit(up[-1] - up[-9]), apex, -du)[1:]]
lo = np.r_[hermite(apex, dl, lo[0], unit(lo[8] - lo[0]))[:-1], lo]
up_bz = bezfit.fit(up, 0.12, t2=du)
lo_bz = bezfit.fit(lo, 0.12, t1=dl)

# ---- compose ------------------------------------------------------------------------------------------------
BIG = "M-100 -100H1100V1100H-100Z"


def poly_d(pts):
    return "M" + "L".join(P(p) for p in pts) + "Z"


def arc(a_from, a_to, sweep):
    """centre-line arc, split in pieces below 180 deg"""
    n = int(abs(a_to - a_from) // 170) + 1
    return "".join(f"A{fmt(R)} {fmt(R)} 0 0 {sweep} {P(circ_pt(a_from + (a_to - a_from) * i / n))}"
                   for i in range(1, n + 1))


a_top = 320 + np.degrees(ext_top / R)
a_bot = 40 - np.degrees(ext_bot / R)
ja = 360 - np.degrees(np.arccos((XA - CX) / R))  # centre circle meets x = XA
ring_a = f"M{P(circ_pt(a_top))}{arc(a_top, ja, 0)}L{P((XA, a_end_y - 8 + ext_a))}"
xb_r = XB + h
a_jb = 360 - np.degrees(np.arccos((xb_r + h + 3 - CX) / R))
ring_b = f"M{P(circ_pt(a_bot))}{arc(a_bot, a_jb, 1)}"
b_top = CY - np.sqrt((R + h + 8) ** 2 - (XB - CX) ** 2)
line_b = f"M{P((XB, b_top))}L{P(corner)}L{P(wave_bz[0][0])}{curve_d(wave_bz)}{fr_s.svg_to(ext_s)}"
hook_d = f"M{P(fr_c1.back(ext_c1, 0))}{fr_c1.svg_to(ext_c1, inward=True)}{curve_d(hook_bz)}{fr_c2.svg_to(ext_c2)}"
v_d = (f"M{P(fr_v1.back(ext_v1, 0))}{fr_v1.svg_to(ext_v1, inward=True)}{curve_d(up_bz)}"
       f"{curve_d(lo_bz)}{fr_v2.svg_to(ext_v2)}")
Ro = R + h
right_of_b = np.array([(xb_r, 200), (320, 200), (320, 330), (xb_r, 330)])

# outer corner of the L: miter join, rounded with a small radius like the original
RC = 4.0
e1 = np.array([0.0, -1.0])                      # from the corner up the left edge
e2 = unit(np.array([1.0, ang[0]]))              # from the corner along the bottom edge
nb = np.array([-e2[1], e2[0]])
nb = nb if nb[1] > 0 else -nb                   # outward (down) normal of the bottom edge
oc_y = (np.polyval(ang, XB - h) + h * np.hypot(1, ang[0]))
Oc = np.array([XB - h, oc_y])
half = np.arccos(np.clip(e1 @ e2, -1, 1)) / 2
bis = unit(e1 + e2)
fc = Oc + bis * RC / np.sin(half)
t1, t2 = Oc + e1 * RC / np.tan(half), Oc + e2 * RC / np.tan(half)
a1, a2 = np.arctan2(*(t1 - fc)[::-1]), np.arctan2(*(t2 - fc)[::-1])
a2 = a1 + (a2 - a1 + np.pi) % (2 * np.pi) - np.pi
arcp = fc + RC * np.c_[np.cos(np.linspace(a1, a2, 9)), np.sin(np.linspace(a1, a2, 9))]
corner_hole = np.r_[[t1 + e1 * 0.01], arcp, [t2 + e2 * 0.01], [Oc - bis * 3]]
print(f"  L outer corner {np.round(Oc, 2)}, rounded with r {RC}")

BIG_P = oriented([(-100, -100), (1100, -100), (1100, 1100), (-100, 1100)], 1)
ELEMENTS = [  # id, path, join, clip base, holes, kept shapes (non-zero winding: base +1, holes -1, kept +1)
    ("ra", ring_a, "miter", BIG_P, [clip_top, clip_a], []),
    ("rb", ring_b, "miter", BIG_P, [clip_bot, right_of_b], []),
    ("lb", line_b, "miter", None, [clip_s, corner_hole], []),
    ("hk", hook_d, "round", BIG_P, [clip_c1, clip_c2], [outline(lab_c)]),
    ("vw", v_d, "miter", BIG_P, [clip_v1, clip_v2], []),
]
disk_pts = oriented(np.c_[CX + Ro * np.cos(np.linspace(0, 2 * np.pi, 8, endpoint=False)),
                          CY + Ro * np.sin(np.linspace(0, 2 * np.pi, 8, endpoint=False))], 1)
# the disk as two arcs; its direction must match the positive orientation of disk_pts
d0, d1 = (CX + Ro, CY), (CX - Ro, CY)
disk = f"M{P(d0)}A{fmt(Ro)} {fmt(Ro)} 0 1 1 {P(d1)}A{fmt(Ro)} {fmt(Ro)} 0 1 1 {P(d0)}Z"


def clip_d(base, holes, kept):
    b = disk if base is None else poly_d(base)
    return (b + "".join(poly_d(oriented(pl, -1)) for pl in holes) + "".join(poly_d(oriented(pl, 1)) for pl in kept))


clips = "".join(f'<clipPath id="g-{i}"><path d="{clip_d(b, hs, ks)}"/></clipPath>' for i, _, _, b, hs, ks in ELEMENTS)
paths = "".join(f'<path clip-path="url(#g-{i})" stroke-linejoin="{j}" d="{d}"/>' for i, d, j, *_ in ELEMENTS)
frag = (f'<defs>{clips}</defs>\n<g id="gold" fill="none" stroke="#d69f31" stroke-width="{fmt(W)}" '
        f'stroke-miterlimit="20">{paths}</g>\n')
open(out_p, "w").write(frag)
nodes = sum(len(re.findall("[MLCA]", d)) for _, d, *_ in ELEMENTS)
print(f"fragment {len(frag)} bytes, {nodes} path nodes")

# ---- raster check against the original -----------------------------------------------------------------------
H_, W_ = G.shape
ys, xs = np.mgrid[0:H_, 0:W_]
X, Y = (xs + 0.5) / K, (ys + 0.5) / K


def sample(d):
    """dense points of a path made of M/L/C/A commands"""
    toks = re.findall(r"[MLCAZ]|-?\d+(?:\.\d+)?", d)
    pts, cur, i = [], None, 0
    while i < len(toks):
        c = toks[i]
        if c == "M":
            cur = np.array([float(toks[i + 1]), float(toks[i + 2])])
            pts.append(cur[None])
            i += 3
        elif c == "L":
            nx = np.array([float(toks[i + 1]), float(toks[i + 2])])
            n = int(np.hypot(*(nx - cur)) / 0.1) + 2
            pts.append(cur + np.linspace(0, 1, n)[:, None] * (nx - cur))
            cur = nx
            i += 3
        elif c == "C":
            b = np.array([cur] + [[float(toks[i + 1 + 2 * k]), float(toks[i + 2 + 2 * k])] for k in range(3)])
            pts.append(bezfit.bez(b, np.linspace(0, 1, 2000)))
            cur = b[3]
            i += 7
        elif c == "A":
            rr = float(toks[i + 1])
            sweep = toks[i + 5] == "1"
            nx = np.array([float(toks[i + 6]), float(toks[i + 7])])
            mid, dd = (cur + nx) / 2, nx - cur
            L = np.hypot(*dd)
            nrm = np.array([-dd[1], dd[0]]) / L
            off = np.sqrt(max(rr * rr - L * L / 4, 0))
            cc = mid + nrm * off * (1 if sweep else -1)  # small arc
            a0 = np.arctan2(cur[1] - cc[1], cur[0] - cc[0])
            a1 = np.arctan2(nx[1] - cc[1], nx[0] - cc[0])
            a1 = a0 + (a1 - a0) % (2 * np.pi) if sweep else a0 - (a0 - a1) % (2 * np.pi)
            a = np.linspace(a0, a1, max(int(abs(a1 - a0) * rr / 0.1), 2))
            pts.append(np.c_[cc[0] + rr * np.cos(a), cc[1] + rr * np.sin(a)])
            cur = nx
            i += 8
        else:
            i += 1
    return np.concatenate(pts)


grid = np.c_[X.ravel(), Y.ravel()]
mine = np.zeros(G.shape, bool)
for i, d, j, base, polys, kept in ELEMENTS:
    sp = sample(d)
    x0, y0 = sp.min(0) - h - 2
    x1, y1 = sp.max(0) + h + 2
    box = (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    g = grid[box.ravel()]
    dist, _ = cKDTree(sp).query(g)
    inside = dist <= h
    hole = np.zeros(len(g), bool)
    for pl in polys:
        hole |= points_in_poly(g, np.array(pl))
    for pl in kept:
        hole &= ~points_in_poly(g, np.array(pl))
    inside &= ~hole
    if base is None:
        inside &= np.hypot(g[:, 0] - CX, g[:, 1] - CY) <= Ro
    m = np.zeros(G.shape, bool)
    m[box] = inside
    mine |= m
orig = cl.soft > 0.5
only_o, only_m = orig & ~mine, mine & ~orig
print(f"pixels: original {orig.sum()}, mine {mine.sum()}, only original {only_o.sum()}, only mine {only_m.sum()}")
rgb = np.full(G.shape + (3,), 255, np.uint8)
rgb[orig & mine] = (120, 120, 120)
rgb[only_o] = (220, 30, 30)
rgb[only_m] = (30, 160, 30)
rows = b"".join(b"\0" + row.tobytes() for row in rgb)
ch = lambda t, x: struct.pack(">I", len(x)) + t + x + struct.pack(">I", zlib.crc32(t + x) & 0xffffffff)
open(f"{dbg}/diff.png", "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", W_, H_, 8, 2, 0, 0, 0)) +
                                    ch(b"IDAT", zlib.compress(rows, 6)) + ch(b"IEND", b""))
