"""Show the finished site in a real, visible browser window and walk through it.

    python tour.py open  <index.html> --x X --y Y --w W --h H --profile DIR --ready FILE --go FILE --script desktop|phone

The window opens in "app" mode (page only, no address bar). The script then
waits until the file given by --go exists (so a screen recording can be started
on the window first), performs the walk-through with the mouse-free browser
automation API, writes a small log with timestamps, and closes the window.
It never changes the HTML file.
"""
import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def smooth_scroll(page, to_y: int, step: int = 420, pause: float = 0.75) -> None:
    y = page.evaluate("window.scrollY")
    direction = 1 if to_y > y else -1
    while (to_y - y) * direction > 0:
        y = y + direction * step
        if (to_y - y) * direction < 0:
            y = to_y
        page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'smooth'}})")
        page.wait_for_timeout(int(pause * 1000))


def run(page, log, kind: str) -> None:
    height = lambda: page.evaluate("document.documentElement.scrollHeight - window.innerHeight")  # noqa: E731
    page.evaluate("localStorage.clear()")
    page.reload()
    page.wait_for_timeout(1500)
    log("start: top of the page, day mode")
    page.wait_for_timeout(2500)

    log("games: hot take roulette, three spins")
    page.locator("#roulette-button").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    for _ in range(3):
        page.locator("#roulette-button").click()
        page.wait_for_timeout(1900)
    log("games: who said it - deal, then reveal")
    page.locator("#quiz-deal").click()
    page.wait_for_timeout(2400)
    page.locator("#quiz-reveal").click()
    page.wait_for_timeout(2400)

    log("scroll down through the five cards to the shared view, day mode")
    smooth_scroll(page, height(), step=300 if kind == "desktop" else 460, pause=0.9 if kind == "desktop" else 0.6)
    page.wait_for_timeout(2500)

    log("back to the top")
    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    page.wait_for_timeout(2200)

    log("click the day/night toggle -> night mode")
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(2600)

    log("scroll down again in night mode")
    smooth_scroll(page, height(), step=520 if kind == "desktop" else 700, pause=0.6 if kind == "desktop" else 0.45)
    page.wait_for_timeout(2500)

    log("back to the top, toggle back to day mode")
    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    page.wait_for_timeout(2000)
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(2200)
    log("end")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["open"])
    ap.add_argument("html")
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--w", type=int, required=True)
    ap.add_argument("--h", type=int, required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--ready", required=True)
    ap.add_argument("--go", required=True)
    ap.add_argument("--script", choices=["desktop", "phone"], default="desktop")
    ap.add_argument("--log", required=True)
    a = ap.parse_args()

    url = Path(a.html).resolve().as_uri()
    for f in (a.ready, a.go):
        Path(f).unlink(missing_ok=True)
    rows = []

    def log(text: str) -> None:
        rows.append({"t": round(time.time(), 2), "clock": time.strftime("%H:%M:%S"), "step": text})
        print(time.strftime("%H:%M:%S"), text, flush=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            a.profile, channel="msedge", headless=False, no_viewport=True,
            chromium_sandbox=True,  # keep the browser sandbox on (also avoids the "--no-sandbox" warning bar)
            ignore_default_args=["--enable-automation"],
            args=[f"--app={url}", f"--window-position={a.x},{a.y}", f"--window-size={a.w},{a.h}",
                  "--no-first-run", "--no-default-browser-check", "--disable-features=msEdgeSidebarV2"])
        page = ctx.pages[0] if ctx.pages else ctx.wait_for_event("page")
        page.wait_for_load_state("load")
        Path(a.ready).write_text(json.dumps({"title": page.title(), "inner": page.evaluate("[innerWidth, innerHeight]")}),
                                 encoding="utf-8")
        print("window is open:", page.title(), page.evaluate("[innerWidth, innerHeight]"), flush=True)
        deadline = time.time() + 180
        while not Path(a.go).exists():
            if time.time() > deadline:
                raise SystemExit("never got the go signal")
            time.sleep(0.3)
        run(page, log, a.script)
        Path(a.log).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print("walk-through finished, waiting for the close signal", flush=True)
        close_file = Path(a.go + ".close")
        deadline = time.time() + 120
        while not close_file.exists() and time.time() < deadline:
            time.sleep(0.3)
        ctx.close()


if __name__ == "__main__":
    main()
