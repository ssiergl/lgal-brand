"""Convert the source image to a 24-bit BMP, the input format of the tracing tools.
Usage: tobmp.py original.png original.bmp"""
import sys

from PIL import Image

Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], "BMP")
