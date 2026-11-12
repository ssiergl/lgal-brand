#!/bin/sh
# Rebuild the logo from source/original.png: tracing and fitting into build/, the finished SVG files
# into logo/, the PNG exports and the social previews into export/. Needs Python 3.12 (vtracer has no wheels for newer
# versions yet) with the packages from tools/requirements.txt. Takes a few minutes.
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
B=build
mkdir -p "$B/debug" logo export
$PY tools/tobmp.py source/original.png "$B/original.bmp"
$PY tools/quantize.py "$B/original.bmp" "$B/flat.png"
$PY tools/trace.py "$B/flat.png" "$B/traced.svg"
$PY tools/clean.py "$B/traced.svg" "$B/flat.json"
$PY tools/circles.py "$B/flat.json" "$B/flat-circ.json"
$PY tools/fish.py "$B/original.bmp" "$B/fish.svg" "$B/debug/fish"
$PY tools/goldmask.py "$B/original.bmp" "$B/gold-mask.npy" "$B/goldness.npy"
$PY tools/strokes.py "$B/gold-mask.npy" "$B/goldness.npy" "$B/gold.svg" "$B/debug"
$PY tools/build.py "$B/flat-circ.json" "$B/fish.svg" "$B/gold.svg" logo
$PY tools/export.py logo export
$PY tools/social.py logo/lgal-plaque.svg "LGAL Doser" 'Professional smart|open-source dosing pump|for reef aquariums' export/lgal-doser-social.png
