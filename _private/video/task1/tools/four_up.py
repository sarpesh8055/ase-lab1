"""Put the four required views of the site on one 1920x1080 slide image.

    python four_up.py <shots-dir> <out.png>

Expects desktop_day.png, desktop_night.png, phone_day.png, phone_night.png in <shots-dir>.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG, FG, MUTED = (17, 17, 24), (244, 241, 222), (160, 158, 176)


def font(size: int, bold: bool = False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def place(canvas, draw, path: Path, box, label: str) -> None:
    x, y, w, h = box
    img = Image.open(path).convert("RGB")
    scale = min(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
    px, py = x + (w - img.width) // 2, y
    draw.rectangle([px - 2, py - 2, px + img.width + 1, py + img.height + 1], outline=(70, 68, 96), width=2)
    canvas.paste(img, (px, py))
    draw.text((px, py + img.height + 8), label, font=font(24), fill=MUTED)


def main() -> None:
    shots, out = Path(sys.argv[1]), Path(sys.argv[2])
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 22), "Our team website: desktop and phone, day and night", font=font(34, bold=True), fill=FG)
    suffix = sys.argv[3] if len(sys.argv) > 3 else ""
    place(canvas, draw, shots / f"desktop_day{suffix}.png", (40, 90, 800, 430), "Desktop, day mode")
    place(canvas, draw, shots / f"desktop_night{suffix}.png", (40, 585, 800, 430), "Desktop, night mode")
    place(canvas, draw, shots / f"phone_day{suffix}.png", (900, 90, 470, 930), "Phone, day mode")
    place(canvas, draw, shots / f"phone_night{suffix}.png", (1410, 90, 470, 930), "Phone, night mode")
    canvas.save(out)
    print(f"{out} {canvas.size}")


if __name__ == "__main__":
    main()
