"""Small screen helper (physical pixels, DPI-aware).

    python screen.py monitors
    python screen.py shot <monitor-index> <out.png> [max_width]

Monitor index 1..n follows mss numbering (0 would be the whole virtual desktop).
"""
import sys

import mss
from PIL import Image


def main() -> None:
    cmd = sys.argv[1]
    with mss.mss() as sct:
        if cmd == "monitors":
            for i, mon in enumerate(sct.monitors):
                label = "virtual desktop" if i == 0 else f"monitor {i}"
                print(f"{label}: left={mon['left']} top={mon['top']} "
                      f"width={mon['width']} height={mon['height']}")
        elif cmd == "shot":
            idx, out = int(sys.argv[2]), sys.argv[3]
            max_w = int(sys.argv[4]) if len(sys.argv) > 4 else 0
            raw = sct.grab(sct.monitors[idx])
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            if max_w and img.width > max_w:
                img = img.resize((max_w, round(img.height * max_w / img.width)), Image.Resampling.LANCZOS)
            img.save(out)
            print(f"monitor {idx}: {raw.size[0]}x{raw.size[1]} -> {out} ({img.width}x{img.height})")
        elif cmd == "rect":
            # python screen.py rect <x> <y> <w> <h> <out.png>   (screen region, e.g. one window)
            x, y, w, h = (int(v) for v in sys.argv[2:6])
            raw = sct.grab({"left": x, "top": y, "width": w, "height": h})
            Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX").save(sys.argv[6])
            print(f"region {w}x{h} at ({x},{y}) -> {sys.argv[6]}")
        else:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
