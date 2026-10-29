"""Generate the neutral brand images (own artwork, not the kitaplus logo).

Usage: python3 scripts/make_brand.py
Writes custom_components/kitaplus/brand/{icon,dark_icon,logo,dark_logo}[@2x].png
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path("custom_components/kitaplus/brand")
SCALE = 4  # draw large, then downsample for smooth edges


def draw_icon(size: int, dark: bool) -> Image.Image:
    big = size * SCALE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (38, 50, 66, 255) if dark else (30, 136, 229, 255)
    fg = (255, 255, 255, 255)
    accent = (255, 193, 7, 255)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big // 5, fill=bg)
    # house
    cx, base = big // 2, int(big * 0.72)
    w = int(big * 0.46)
    d.polygon(
        [
            (cx - w // 2 - big // 20, int(big * 0.46)),
            (cx, int(big * 0.22)),
            (cx + w // 2 + big // 20, int(big * 0.46)),
        ],
        fill=fg,
    )
    d.rectangle([cx - w // 2, int(big * 0.46), cx + w // 2, base], fill=fg)
    # door and a small "child" figure in the accent colour
    door = int(big * 0.09)
    d.rectangle([cx - door, int(big * 0.56), cx + door, base], fill=bg)
    r = int(big * 0.055)
    d.ellipse([cx - r, int(big * 0.49) - r, cx + r, int(big * 0.49) + r], fill=accent)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for dark in (False, True):
        prefix = "dark_" if dark else ""
        for kind, base in (("icon", 256), ("logo", 256)):
            draw_icon(base, dark).save(OUT / f"{prefix}{kind}.png")
            draw_icon(base * 2, dark).save(OUT / f"{prefix}{kind}@2x.png")
    print("ok", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
