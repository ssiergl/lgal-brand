"""Gold parts of the original: a binary mask and a continuous "goldness" (0 = navy, 1 = gold) for
sub-pixel edges. The fish's yellow fin is excluded.
Usage: goldmask.py original.bmp gold-mask.npy goldness.npy"""
import struct
import sys

import numpy as np
from scipy import ndimage

d = open(sys.argv[1], "rb").read()
off = struct.unpack_from("<I", d, 10)[0]
W, H = struct.unpack_from("<ii", d, 18)
bu = H > 0
H = abs(H)
st = (W * 3 + 3) & ~3
img = np.frombuffer(d, np.uint8, count=st * H, offset=off).reshape(H, st)[:, :W * 3].reshape(H, W, 3)[:, :, ::-1]
img = (img[::-1] if bu else img).astype(np.float32)
K = W / 1000
ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
X, Y = (xs + 0.5) / K, (ys + 0.5) / K
PAL = np.array([(13, 38, 59), (53, 149, 162), (214, 159, 49), (251, 251, 249)], np.float32)
near = np.argmin(((img[:, :, None, :] - PAL[None, None]) ** 2).sum(-1), -1)
gold = near == 2
LINE = [(140, 2000), (300, 760), (315, 660), (350, 612), (400, 564), (450, 541), (550, 522), (600, 500), (2000, 0)]
line_x = np.interp(Y, [p[0] for p in LINE], [p[1] for p in LINE])
in_fish = ((X - 505) ** 2 + (Y - 330) ** 2 <= 186 ** 2) & (X < line_x)
ring = np.abs(np.hypot(X - 509.8, Y - 488.7) - 352.6) < 16
gold &= ~in_fish | (np.abs(X - line_x) < 26) | ring
gold = ndimage.binary_opening(gold, iterations=2)
gold = ndimage.binary_closing(gold, iterations=2)
np.save(sys.argv[2], gold)
NAVY, GOLD = PAL[0], PAL[2]
g = ((img - NAVY) @ (GOLD - NAVY)) / ((GOLD - NAVY) @ (GOLD - NAVY))
g = np.clip(g, 0, 1) * ndimage.binary_dilation(gold, iterations=6)
np.save(sys.argv[3], g.astype(np.float32))
