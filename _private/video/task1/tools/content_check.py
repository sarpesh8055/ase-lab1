"""Compare what the profiles say with what the page shows (read-only).

    python content_check.py <content-dir> <index.html>

For every profile section it reports whether the text appears on the page word for
word, and prints the profile text next to nothing else when it does not.
"""
import html
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def page_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"data:image/[\w.+-]+;base64,[A-Za-z0-9+/=]+", "", raw)
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S)
    return norm(re.sub(r"<[^>]+>", " ", raw))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    content, page = Path(sys.argv[1]), page_text(Path(sys.argv[2]))
    total = exact = 0
    for md in sorted(content.glob("*.md")):
        if md.name.startswith("_"):
            continue
        text = re.sub(r"<!--.*?-->", "", md.read_text(encoding="utf-8"), flags=re.S)
        name = re.search(r"^# (.+)$", text, re.M).group(1).strip()
        print(f"\n== {name} ({md.name}) - name on page: {norm(name) in page}")
        for title, body in re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M):
            pieces = [p.strip().lstrip("-").strip() for p in body.strip().splitlines() if p.strip()]
            for piece in pieces:
                total += 1
                if norm(piece) in page:
                    exact += 1
                else:
                    words = [w for w in re.findall(r"[a-zA-Z]{5,}", piece.lower())]
                    found = sum(1 for w in words if w in page)
                    print(f"   NOT word for word [{title.strip()}]: \"{piece[:150]}\""
                          f"  ({found}/{len(words)} of its longer words are on the page)")
    print(f"\n{exact} of {total} profile statements appear on the page word for word.")


if __name__ == "__main__":
    main()
