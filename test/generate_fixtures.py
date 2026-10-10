#!/usr/bin/env python3
"""Deterministic fictional strokes; never reads or traces real handwriting."""
from pathlib import Path
import math
from PIL import Image, ImageDraw


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    w, h, upscale = 420, 180, 3
    for name, rule in (("sig-a", True), ("sig-b", False)):
        # Grayscale RGB keeps luminance rounding consistent across implementations.
        background = Image.new("RGB", (w, h))
        background.putdata([(round(232 + 12*x/w + 4*y/h),)*3
                            for y in range(h) for x in range(w)])
        image = background.resize((w*upscale, h*upscale), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(image)
        points = []
        for n in range(601):
            t = n/600 * math.pi * 4
            x = 55 + 300*n/600 + 19*math.sin(3*t)
            y = 90 + 37*math.sin(2*t) + 9*math.cos(5*t)
            points.append((round(x*upscale), round(y*upscale)))
        draw.line(points, fill=(35,)*3, width=5*upscale, joint="curve")
        draw.line([(65*upscale,145*upscale),(95*upscale,45*upscale)],
                  fill=(35,)*3, width=4*upscale)
        if rule:
            draw.line([(20*upscale,120*upscale),(400*upscale,120*upscale)],
                      fill=(45,)*3, width=2*upscale)
        image.resize((w,h), Image.Resampling.LANCZOS).save(output/f"{name}.png")


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent / "fixtures")
