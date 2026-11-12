#!/usr/bin/env python3
"""Compose the logo files from the flat parts (flat.json: teal and white areas, exact outer arcs),
the fish fragment and the gold strokes.

  lgal-plaque.svg  the logo: round navy plaque with transparent corners (use this one)
  lgal-badge.svg   the same on a navy square with rounded corners (avatars, social images)

Path coordinates are rounded to 0.1 (logo units: 1000 = width of the original).
Usage: build.py flat.json fish.svg gold.svg outdir"""
import json
import re
import sys

NAVY, TEAL, GOLD, WHITE = "#0d263b", "#3595a2", "#d69f31", "#fbfbf9"
FLAT_FISH = {"url(#f-body)": "#2f8c9c", "url(#f-eye)": "#5fc4ba", "url(#f-belly)": "#e2f1f3",
             "url(#f-fin)": "#f2a663"}
DISC = (507.59, 488.0, 497)  # navy disc around the ring text (text reaches r 465)
BADGE_RX = 180  # corner radius of the badge (18 % of its width)
DISC_VIEW = f"{DISC[0] - DISC[2]:.2f} {DISC[1] - DISC[2]:.2f} {2 * DISC[2]} {2 * DISC[2]}"

paths = json.load(open(sys.argv[1]))
fish_src = open(sys.argv[2]).read()
gold_src = open(sys.argv[3]).read()
out = sys.argv[4]
gold_defs = re.search(r"<defs>(.*?)</defs>", gold_src, re.S).group(1)
gold = re.search(r'<g id="gold".*?</g>', gold_src, re.S).group(0)
defs = re.search(r"<defs>.*?</defs>", fish_src, re.S).group(0).replace("</defs>", gold_defs + "</defs>")
fish = re.search(r'<g id="fish">.*</g>', fish_src, re.S).group(0)


def fish_layer(flat):
    if not flat:
        return fish
    f = fish.replace('<g fill="url(#f-rim)">', '<g fill="none" display="none">')  # light overlay only
    for k, v in FLAT_FISH.items():
        f = f.replace(f'fill="{k}"', f'fill="{v}"')
    return f


def flat_group(colour, fill, outer):
    def keep(p):
        return p["c"] == colour and (outer is None or p["outer"] == outer)
    ds = "".join(p["d"] for p in paths if keep(p))
    return f'<path fill="{fill}" fill-rule="evenodd" d="{ds}"/>' if ds else ""


def svg(text=WHITE, bg=None, outer=True, flat=False, view="0 0 1000 1000", size=1000, title="LG Aquatic Life",
        disc=False):
    body = [f'<title>{title}</title>']
    body.append(defs if not flat else f"<defs>{gold_defs}</defs>")
    if disc:
        body.append(f'<circle cx="{DISC[0]}" cy="{DISC[1]}" r="{DISC[2]}" fill="{NAVY}"/>')
    if bg:
        body.append(f'<rect width="1000" height="1000" rx="{BADGE_RX}" fill="{bg}"/>')
    body.append(fish_layer(flat))
    body.append(flat_group("teal", TEAL, None if outer else False))
    body.append(gold)
    body.append(flat_group("white", WHITE, False))
    if outer:
        body.append(flat_group("white", text, True))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="{size}" height="{size}">'
            + "\n".join(b for b in body if b) + "</svg>\n")


def compact(svg_text):
    """round the numbers inside path data to one decimal"""
    def num(n):
        t = f"{float(n.group(0)):.1f}"
        nxt = n.string[n.end():n.end() + 1]
        if nxt != ".":  # "1.0" may drop its ".0" unless a ".5"-style number follows directly
            t = t.rstrip("0").rstrip(".")
        return "0" if t in ("", "-0") else t
    return re.sub(r' (?:d|points)="[^"]*"', lambda m: re.sub(r"-?\d*\.\d+", num, m.group(0)), svg_text)


files = {
    "lgal-plaque.svg": svg(disc=True, view=DISC_VIEW, size=512),
    "lgal-badge.svg": svg(bg=NAVY, size=512),
}
for name, content in files.items():
    content = compact(content)
    open(f"{out}/{name}", "w").write(content)
    print(f"{name:16} {len(content):7} bytes")
