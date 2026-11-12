"""Cubic Bezier fitting of a point sequence (Schneider, Graphics Gems I)."""
import numpy as np


def bez(P, t):
    t = np.asarray(t)[:, None]
    m = 1 - t
    return m ** 3 * P[0] + 3 * m * m * t * P[1] + 3 * m * t * t * P[2] + t ** 3 * P[3]


def _d1(P, t):
    t = np.asarray(t)[:, None]
    m = 1 - t
    return 3 * (m * m * (P[1] - P[0]) + 2 * m * t * (P[2] - P[1]) + t * t * (P[3] - P[2]))


def _d2(P, t):
    t = np.asarray(t)[:, None]
    return 6 * ((1 - t) * (P[2] - 2 * P[1] + P[0]) + t * (P[3] - 2 * P[2] + P[1]))


def _gen(d, u, t1, t2):
    A1 = (3 * (1 - u) ** 2 * u)[:, None] * t1
    A2 = (3 * (1 - u) * u ** 2)[:, None] * t2
    C = np.array([[(A1 * A1).sum(), (A1 * A2).sum()], [(A1 * A2).sum(), (A2 * A2).sum()]])
    tmp = d - bez(np.array([d[0], d[0], d[-1], d[-1]]), u)
    X = np.array([(A1 * tmp).sum(), (A2 * tmp).sum()])
    seg = np.hypot(*(d[-1] - d[0]))
    try:
        a1, a2 = np.linalg.solve(C, X)
    except np.linalg.LinAlgError:
        a1 = a2 = seg / 3
    if a1 < 1e-6 * seg or a2 < 1e-6 * seg:
        a1 = a2 = seg / 3
    return np.array([d[0], d[0] + a1 * t1, d[-1] + a2 * t2, d[-1]])


def _err(d, P, u):
    e = np.hypot(*(bez(P, u) - d).T)
    i = int(np.argmax(e))
    return e[i], i


def _reparam(d, P, u):
    q, q1, q2 = bez(P, u) - d, _d1(P, u), _d2(P, u)
    num = (q * q1).sum(1)
    den = (q1 * q1).sum(1) + (q * q2).sum(1)
    return np.clip(u - np.where(np.abs(den) > 1e-12, num / den, 0), 0, 1)


def _unit(v):
    return v / np.hypot(*v)


def fit(d, tol, t1=None, t2=None):
    d = np.asarray(d, float)
    t1 = _unit(d[min(3, len(d) - 1)] - d[0]) if t1 is None else t1
    t2 = _unit(d[max(len(d) - 4, 0)] - d[-1]) if t2 is None else t2
    return _fit(d, t1, t2, tol)


def _fit(d, t1, t2, tol):
    if len(d) == 2:
        s = np.hypot(*(d[1] - d[0])) / 3
        return [np.array([d[0], d[0] + s * t1, d[1] + s * t2, d[1]])]
    c = np.r_[0, np.cumsum(np.hypot(*np.diff(d, axis=0).T))]
    u = c / c[-1]
    P = _gen(d, u, t1, t2)
    e, i = _err(d, P, u)
    if e < tol:
        return [P]
    if e < tol * 8:
        for _ in range(30):
            u = _reparam(d, P, u)
            P = _gen(d, u, t1, t2)
            e, i = _err(d, P, u)
            if e < tol:
                return [P]
    i = min(max(i, 1), len(d) - 2)
    tc = _unit(d[i - 1] - d[i + 1])
    return _fit(d[:i + 1], t1, tc, tol) + _fit(d[i:], -tc, t2, tol)
