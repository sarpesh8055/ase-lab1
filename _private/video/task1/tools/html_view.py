"""Print an HTML file with embedded base64 data cut out, so it can be read (never edits it).

    python html_view.py <file.html> [start-line] [end-line]
"""
import re
import sys


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = open(sys.argv[1], encoding="utf-8").read()
    text = re.sub(r"data:image/[\w.+-]+;base64,[A-Za-z0-9+/=]+",
                  lambda m: f"data:image/…;base64,<{len(m.group(0)) // 1024} KB cut>", text)
    lines = text.splitlines()
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else len(lines)
    print(f"# {len(lines)} lines, {len(text) / 1024:.0f} KB without the pictures")
    for number, line in enumerate(lines[start - 1:end], start):
        print(f"{number:4}: {line[:400]}{' …' if len(line) > 400 else ''}")


if __name__ == "__main__":
    main()
