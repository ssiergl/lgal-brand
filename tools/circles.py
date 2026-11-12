#!/usr/bin/env python3
"""Replace the traced outer teal arcs by exact circular arcs with round ends (fitted to the original).
Usage: circles.py in.json out.json"""
import json
import math
import sys

CX, CY, R, W = 507.59, 488.0, 423.24, 15.81
ARCS = [(-36.62, 25.07), (155.0, 214.22)]  # cap centre angles in degrees, y down


def pt(rad, deg):
    a = math.radians(deg)
    return f"{CX + rad * math.cos(a):.2f} {CY + rad * math.sin(a):.2f}"


def arc_path(a0, a1):
    ro, ri, h = R + W / 2, R - W / 2, W / 2
    large = 1 if a1 - a0 > 180 else 0
    return (f"M{pt(ro, a0)}A{ro} {ro} 0 {large} 1 {pt(ro, a1)}"
            f"A{h} {h} 0 0 1 {pt(ri, a1)}"
            f"A{ri} {ri} 0 {large} 0 {pt(ri, a0)}"
            f"A{h} {h} 0 0 1 {pt(ro, a0)}Z")


paths = [p for p in json.load(open(sys.argv[1])) if not (p["c"] == "teal" and p["outer"])]
for a0, a1 in ARCS:
    paths.append({"c": "teal", "outer": True, "d": arc_path(a0, a1),
                  "bb": [CX - R - W, CY - R - W, CX + R + W, CY + R + W]})
json.dump(paths, open(sys.argv[2], "w"))
