"""Social preview image (1280 x 640, e.g. for GitHub) for one product: plaque, title, subtitle.
Usage: social.py lgal-plaque.svg "Title" "Subtitle, | starts a new line" out.png"""
import re
import sys

import resvg_py

plaque, title, subtitle, out = sys.argv[1:5]
NAVY, GOLD, WHITE, TEAL_LIGHT = "#0d263b", "#d69f31", "#fbfbf9", "#9fd3da"
FONT = "Montserrat, 'Avenir Next', 'Helvetica Neue', Arial, sans-serif"

p = open(plaque).read()
view = re.search(r'viewBox="([^"]+)"', p).group(1)
inner = re.search(r"<svg[^>]*>(.*)</svg>", p, re.S).group(1)
lines = [t.strip() for t in subtitle.split("|")]
sub = "".join(f'<tspan x="640" dy="{0 if i == 0 else 52}">{t}</tspan>' for i, t in enumerate(lines))
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640">
<rect width="1280" height="640" fill="{NAVY}"/>
<svg x="60" y="60" width="520" height="520" viewBox="{view}">{inner}</svg>
<text x="640" y="270" fill="{WHITE}" font-family="{FONT}" font-weight="700" font-size="92">{title}</text>
<rect x="644" y="306" width="120" height="8" rx="4" fill="{GOLD}"/>
<text x="640" y="380" fill="{TEAL_LIGHT}" font-family="{FONT}" font-weight="500" font-size="40">{sub}</text>
</svg>"""
png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
open(out, "wb").write(png)
print(out, len(png), "bytes")
