"""Look at the generated site in a real browser (read-only: never changes the HTML).

    python site.py shots <index.html> <out-dir> [--tag NAME]
        Screenshots: desktop and phone, day and night, each as "first screen" and "whole page".
        Night mode is switched on by clicking the page's own toggle button.
    python site.py audit <index.html>
        Layout facts a reviewer would check: horizontal overflow, console errors,
        external requests, image sizes, toggle behaviour, contrast of text colours.
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
TOGGLE = "#theme-toggle, [data-theme-toggle], button[aria-label*='theme' i], button[class*='theme' i], button[id*='theme' i]"


def open_page(pw, viewport, scale=1, mobile=False, headless=True, args=None):
    browser = pw.chromium.launch(channel="msedge", headless=headless, args=args or [])
    context = browser.new_context(viewport=viewport, device_scale_factor=scale, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    return browser, page


def theme_of(page) -> str:
    return page.evaluate("document.documentElement.getAttribute('data-theme') || document.body.className || ''")


def cmd_shots(a) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    url = Path(a.html).resolve().as_uri()
    tag = f"{a.tag}_" if a.tag else ""
    with sync_playwright() as pw:
        for device, viewport, scale, mobile in (("desktop", DESKTOP, 1, False), ("phone", PHONE, 2, True)):
            browser, page = open_page(pw, viewport, scale, mobile)
            page.goto(url)
            page.wait_for_load_state("load")
            page.evaluate("localStorage.clear()")
            page.reload()
            page.wait_for_timeout(400)
            for mode in ("day", "night"):
                if mode == "night":
                    page.locator(TOGGLE).first.click()
                    page.wait_for_timeout(500)
                # walk down the page once so anything that loads on scroll is there
                height = page.evaluate("document.documentElement.scrollHeight")
                for y in range(0, height, 600):
                    page.evaluate(f"window.scrollTo(0, {y})")
                    page.wait_for_timeout(60)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(300)
                first = out / f"{tag}{device}_{mode}.png"
                whole = out / f"{tag}{device}_{mode}_full.png"
                page.screenshot(path=str(first))
                page.screenshot(path=str(whole), full_page=True)
                # a third view: scrolled down to the member cards, so the pictures are visible
                page.evaluate("""() => { const el = document.querySelector('.team-grid, .member-card, #team');
                    if (el) window.scrollTo({top: el.getBoundingClientRect().top + window.scrollY - 16, behavior: 'instant'}); }""")
                page.wait_for_timeout(350)
                page.screenshot(path=str(out / f"{tag}{device}_{mode}_cards.png"))
                print(f"{device} {mode}: data-theme={theme_of(page)!r} -> {first.name}, {whole.name}")
            browser.close()


AUDIT_JS = r"""
() => {
  const doc = document.documentElement;
  const wide = [...document.querySelectorAll('body *')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && (r.right > doc.clientWidth + 1 || r.left < -1);
  }).slice(0, 8).map(el => el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '') +
       ' right=' + Math.round(el.getBoundingClientRect().right));
  const imgs = [...document.images].map(i => ({alt: i.alt, natural: i.naturalWidth + 'x' + i.naturalHeight,
       shown: Math.round(i.getBoundingClientRect().width) + 'x' + Math.round(i.getBoundingClientRect().height),
       embedded: i.src.startsWith('data:')}));
  const small = [...document.querySelectorAll('body *')].filter(el => el.children.length === 0 && el.textContent.trim())
       .map(el => parseFloat(getComputedStyle(el).fontSize)).filter(px => px < 12).length;
  return {viewport: doc.clientWidth, scrollWidth: doc.scrollWidth, overflowing: wide, images: imgs,
          textNodesUnder12px: small, buttons: document.querySelectorAll('button').length,
          interactive: document.querySelectorAll('button, a[href], input, select, details, [onclick], [tabindex]').length,
          headings: [...document.querySelectorAll('h1,h2')].map(h => h.textContent.trim().slice(0, 70))};
}
"""

CONTRAST_JS = r"""
() => {
  const lum = c => { const v = c.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
                     return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const parse = s => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null;
                       const p = m[1].split(/[ ,/]+/).map(parseFloat); return {rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1}; };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor);
                       if (c && c.a > 0.5) return c.rgb; } return [255, 255, 255]; };
  const worst = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length || !el.textContent.trim()) continue;
    const st = getComputedStyle(el); const fg = parse(st.color); if (!fg) continue;
    if (parseFloat(st.opacity) < 1 || el.closest('[style*="opacity"]')) continue;
    const a = lum(fg.rgb), b = lum(bgOf(el)); const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (ratio < 4.5) worst.push({ratio: Math.round(ratio * 100) / 100, text: el.textContent.trim().slice(0, 40),
                                 tag: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '')});
  }
  worst.sort((x, y) => x.ratio - y.ratio);
  return {below_4_5: worst.length, worst: worst.slice(0, 8)};
}
"""


def cmd_audit(a) -> None:
    url = Path(a.html).resolve().as_uri()
    report = {}
    with sync_playwright() as pw:
        for device, viewport, mobile in (("desktop", DESKTOP, False), ("phone", PHONE, True), ("small phone", {"width": 320, "height": 640}, True)):
            browser, page = open_page(pw, viewport, 1, mobile)
            errors, requests = [], []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("request", lambda r: requests.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
            page.goto(url)
            page.wait_for_load_state("load")
            page.evaluate("localStorage.clear()")
            page.reload()
            page.wait_for_timeout(300)
            facts = page.evaluate(AUDIT_JS)
            facts["console_errors"], facts["external_requests"] = errors, requests
            facts["contrast_day"] = page.evaluate(CONTRAST_JS)
            before = theme_of(page)
            toggle = page.locator(TOGGLE).first
            label_before = toggle.inner_text()
            toggle.click()
            page.wait_for_timeout(400)
            facts["toggle"] = {"before": before, "after": theme_of(page), "label_before": label_before,
                               "label_after": toggle.inner_text()}
            facts["contrast_night"] = page.evaluate(CONTRAST_JS)
            page.reload()
            page.wait_for_timeout(300)
            facts["toggle"]["after_reload"] = theme_of(page)
            facts["toggle"]["label_after_reload"] = page.locator(TOGGLE).first.inner_text()
            if device != "desktop":
                facts.pop("images", None)
                facts.pop("headings", None)
            report[device] = facts
            browser.close()
    print(json.dumps(report, indent=1, ensure_ascii=False))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shots")
    s.add_argument("html")
    s.add_argument("out")
    s.add_argument("--tag", default="")
    au = sub.add_parser("audit")
    au.add_argument("html")
    a = ap.parse_args()
    {"shots": cmd_shots, "audit": cmd_audit}[a.cmd](a)


if __name__ == "__main__":
    main()
