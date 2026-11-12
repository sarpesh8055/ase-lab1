from pathlib import Path
import re

source = Path("src/index.html").read_text(encoding="utf-8")
output = Path("site/index.html").read_text(encoding="utf-8")
img_tags = re.findall(r"<img\b[^>]*>", output)
checks = {
    "source has five named placeholders": source.count("{{image:") == 5,
    "source has no lazy-loading markup": 'loading="lazy"' not in source,
    "output has five image tags": len(img_tags) == 5,
    "output has no quoted lazy-loading attributes": not re.search(r"\bloading\s*=\s*(['\"])lazy\1", output, re.I),
    "output has five embedded image data URIs": sum('src="data:image/' in tag for tag in img_tags) == 5,
    "runtime loading workaround is absent": "querySelectorAll" not in output and "removeAttribute('loading')" not in output,
    "opinion sections use one full-width column": ".details { display: grid; grid-template-columns: minmax(0, 1fr);" in output,
}
for description, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {description}")
if not all(checks.values()):
    raise SystemExit(1)
