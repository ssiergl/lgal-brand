"""Colour trace of the flattened logo (flat.png -> traced.svg) with vtracer.
Usage: trace.py flat.png traced.svg"""
import os, sys, time, vtracer
src, dst = sys.argv[1], sys.argv[2]
t = time.time()
vtracer.convert_image_to_svg_py(src, dst, colormode="color", hierarchical="cutout", mode="spline",
    filter_speckle=10, color_precision=8, layer_difference=24, corner_threshold=60, length_threshold=4.0,
    max_iterations=10, splice_threshold=45, path_precision=2)
print("traced", os.path.getsize(dst), "bytes", round(time.time() - t, 1), "s")
