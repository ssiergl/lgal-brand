"""PNG exports of the logo files (rendered with resvg).
Usage: export.py logo_dir export_dir"""
import sys

import resvg_py

SIZES = {"lgal-plaque": (256, 512, 1024), "lgal-badge": (1024,)}

src, dst = sys.argv[1:3]
for name, sizes in SIZES.items():
    for px in sizes:
        png = bytes(resvg_py.svg_to_bytes(svg_path=f"{src}/{name}.svg", width=px, height=px))
        open(f"{dst}/{name}-{px}.png", "wb").write(png)
        print(f"{name}-{px}.png {len(png):8} bytes")
