"""Tiny Win32 window helper (stdlib only, physical pixels).

    python win.py find  <title-substring>            list matching visible windows as JSON
    python win.py wait  <title-substring> [seconds]  wait until one appears, print it as JSON
    python win.py rect  <hwnd>
    python win.py move  <hwnd> <x> <y> <w> <h>       move/resize without activating
    python win.py close <hwnd>                       ask the window to close (WM_CLOSE)
"""
import ctypes
import json
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

try:  # per-monitor DPI awareness, so all numbers are real pixels
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:  # noqa: BLE001 - older Windows
    user32.SetProcessDPIAware()

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsIconic.argtypes = [wintypes.HWND]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
WM_CLOSE = 0x0010
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def rect_of(hwnd: int) -> dict:
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top}


def describe(hwnd: int) -> dict:
    n = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, title, n + 1)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return {"hwnd": hwnd, "title": title.value, "class": cls.value, "pid": pid.value,
            "minimized": bool(user32.IsIconic(hwnd)), **rect_of(hwnd)}


def find(substr: str) -> list[dict]:
    found: list[dict] = []

    @EnumWindowsProc
    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            info = describe(hwnd)
            if substr.lower() in info["title"].lower():
                found.append(info)
        return True

    user32.EnumWindows(callback, 0)
    return found


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "find":
        print(json.dumps(find(sys.argv[2])))
    elif cmd == "wait":
        deadline = time.time() + (float(sys.argv[3]) if len(sys.argv) > 3 else 20)
        while time.time() < deadline:
            hits = find(sys.argv[2])
            if hits:
                print(json.dumps(hits[0]))
                return
            time.sleep(0.3)
        raise SystemExit(f"no visible window with '{sys.argv[2]}' in its title")
    elif cmd == "rect":
        print(json.dumps(describe(int(sys.argv[2]))))
    elif cmd == "move":
        hwnd, x, y, w, h = (int(v) for v in sys.argv[2:7])
        user32.SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)
        print(json.dumps(describe(hwnd)))
    elif cmd == "close":
        user32.PostMessageW(int(sys.argv[2]), WM_CLOSE, 0, 0)
        print("close requested")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
