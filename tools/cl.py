"""Centre-line helpers on the gold mask (2000 px, K = 2 px per unit)."""
from collections import deque

import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize

K = 2
gold = None
soft = None
sk = None


def load(path):
    global gold, soft, sk
    gold = np.load(path)
    soft = ndimage.gaussian_filter(gold.astype(np.float32), 1.0)
    sk = skeletonize(gold)


def nearest_skel(p):
    ys, xs = np.nonzero(sk)
    i = np.argmin((xs - p[0] * K) ** 2 + (ys - p[1] * K) ** 2)
    return ys[i], xs[i]


def skel_path(a, b, avoid=None):
    """shortest skeleton path between two points given in units -> N x 2 units (x, y)"""
    s, t = nearest_skel(a), nearest_skel(b)
    prev = {s: None}
    q = deque([s])
    while q:
        c = q.popleft()
        if c == t:
            break
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                n = (c[0] + dy, c[1] + dx)
                if n not in prev and sk[n] and (avoid is None or not avoid(n[1] / K, n[0] / K)):
                    prev[n] = c
                    q.append(n)
    out, c = [], t
    while c is not None:
        out.append(c)
        c = prev[c]
    out = np.array(out[::-1], float)
    return np.c_[(out[:, 1] + 0.5) / K, (out[:, 0] + 0.5) / K]


def crossings(p, nrm, reach=20):
    """edges of the stroke along the normal through p (units): returns (left offset, right offset)"""
    t = np.arange(-reach, reach, 0.05)
    xs = (p[0] + t * nrm[0]) * K - 0.5
    ys = (p[1] + t * nrm[1]) * K - 0.5
    v = ndimage.map_coordinates(soft, [ys, xs], order=1)
    c = len(t) // 2
    inside = v > 0.5
    if not inside[c]:
        return None
    i = c
    while i > 0 and inside[i - 1]:
        i -= 1
    j = c
    while j < len(t) - 1 and inside[j + 1]:
        j += 1
    if i == 0 or j == len(t) - 1:
        return None
    lo = t[i - 1] + (0.5 - v[i - 1]) / (v[i] - v[i - 1]) * 0.05
    hi = t[j] + (v[j] - 0.5) / (v[j] - v[j + 1]) * 0.05
    return lo, hi


def refine(path, step=1.0, k=4.0):
    """mid points between both edges along the normal; returns points, widths"""
    seg = np.hypot(*np.diff(path, axis=0).T)
    sl = np.r_[0, np.cumsum(seg)]
    s = np.arange(0, sl[-1], step)
    p = np.c_[np.interp(s, sl, path[:, 0]), np.interp(s, sl, path[:, 1])]
    p = ndimage.gaussian_filter1d(p, 2, axis=0, mode="nearest")
    n = int(k / step)
    out, wid = [], []
    for i in range(len(p)):
        a, b = p[max(i - n, 0)], p[min(i + n, len(p) - 1)]
        tg = (b - a) / np.hypot(*(b - a))
        nrm = np.array([-tg[1], tg[0]])
        c = crossings(p[i], nrm)
        if c is None:
            out.append((np.nan, np.nan))
            wid.append(np.nan)
            continue
        out.append(p[i] + nrm * (c[0] + c[1]) / 2)
        wid.append(c[1] - c[0])
    global last_base
    last_base = p
    return np.array(out), np.array(wid)
