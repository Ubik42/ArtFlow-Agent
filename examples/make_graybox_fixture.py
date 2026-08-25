from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

WIDTH = 768
HEIGHT = 512
OUTPUT = Path(__file__).parent / "assets" / "coastal-ruins-graybox.png"
MASK_OUTPUT = Path(__file__).parent / "assets" / "coastal-ruins-arch-mask.png"


def build_fixture() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#9aa1a4")
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        value = int(178 - y * 0.11)
        draw.line((0, y, WIDTH, y), fill=(value, value + 5, value + 8))

    draw.polygon(
        [(0, 330), (155, 276), (315, 321), (470, 248), (768, 315), (768, 512), (0, 512)],
        fill="#61696a",
    )
    draw.polygon(
        [(0, 376), (210, 338), (401, 372), (578, 324), (768, 352), (768, 512), (0, 512)],
        fill="#464e50",
    )
    draw.polygon([(292, 512), (360, 350), (430, 340), (534, 512)], fill="#8b8981")
    draw.polygon([(333, 512), (383, 357), (410, 352), (475, 512)], fill="#b0ada2")

    draw.rectangle((278, 198, 475, 347), fill="#747979", outline="#303638", width=5)
    draw.rectangle((304, 224, 449, 347), fill="#858989", outline="#363b3c", width=4)
    draw.arc((334, 228, 420, 354), 180, 360, fill="#2b3032", width=9)
    draw.rectangle((343, 291, 411, 347), fill="#343a3b")
    draw.rectangle((253, 170, 302, 347), fill="#686e6f", outline="#303638", width=5)
    draw.rectangle((450, 149, 492, 347), fill="#686e6f", outline="#303638", width=5)
    draw.polygon([(247, 170), (310, 170), (299, 143), (259, 151)], fill="#555c5d")
    draw.polygon([(444, 149), (500, 149), (487, 124), (455, 136)], fill="#555c5d")

    draw.polygon([(0, 365), (155, 342), (235, 357), (0, 420)], fill="#293f45")
    for x in range(12, 238, 28):
        draw.line((x, 374, x + 20, 408), fill="#789096", width=2)

    random.seed(42)
    for _ in range(48):
        x = random.randint(35, 720)
        y = random.randint(328, 468)
        if 280 < x < 535:
            continue
        radius = random.randint(2, 7)
        shade = random.randint(66, 96)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=(shade, shade + 5, shade + 4)
        )

    image = image.filter(ImageFilter.GaussianBlur(radius=0.35))
    return image


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    build_fixture().save(OUTPUT, optimize=True)
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((321, 215, 433, 365), fill=255)
    mask_draw.rectangle((321, 278, 433, 365), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=4))
    mask.save(MASK_OUTPUT, optimize=True)
    print(OUTPUT)
    print(MASK_OUTPUT)
