"""Record ONE window (nothing else on the screen) with ffmpeg until a stop file appears.

    python rec.py video <out.mkv> --hwnd <n> --stop-file <path> [--fps 15] [--max-seconds 3600]
    python rec.py still <out.png> --hwnd <n>
    python rec.py to-mp4 <in.mkv> <out.mp4>

The capture uses Windows' per-window capture, so other windows, the taskbar and
notifications can never end up in the file, even if they cover the window.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path


def source(hwnd: str, fps: int) -> str:
    return f"gfxcapture=hwnd={hwnd}:max_framerate={fps}:capture_cursor=0:width=-2:height=-2"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["video", "still", "to-mp4"])
    ap.add_argument("out")
    ap.add_argument("out2", nargs="?")
    ap.add_argument("--hwnd")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--stop-file")
    ap.add_argument("--max-seconds", type=int, default=3600)
    a = ap.parse_args()
    base = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]

    if a.mode == "to-mp4":
        cmd = base + ["-i", a.out, "-c", "copy", "-movflags", "+faststart", a.out2]
        raise SystemExit(subprocess.run(cmd).returncode)

    if a.mode == "still":
        # Note: do not use while a video capture of the same window is running;
        # the second capture session writes its frame but then never exits.
        cmd = base + ["-f", "lavfi", "-i", source(a.hwnd, 5), "-vf", "hwdownload,format=bgra",
                      "-frames:v", "1", "-update", "1", a.out]
        proc = subprocess.Popen(cmd)
        try:
            raise SystemExit(proc.wait(20))
        except subprocess.TimeoutExpired:
            proc.kill()
            raise SystemExit(f"still capture hung and was killed (file written: {Path(a.out).exists()})")

    stop = Path(a.stop_file)
    stop.unlink(missing_ok=True)
    cmd = base + ["-f", "lavfi", "-i", source(a.hwnd, a.fps),
                  "-vf", "hwdownload,format=bgra,format=yuv420p", "-r", str(a.fps),
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  # Write every packet to disk at once. A still window sends no new frames, so
                  # ffmpeg may not notice the stop key and has to be ended the hard way; without
                  # this flag the last minutes would still sit in its write buffer and be lost.
                  "-flush_packets", "1",
                  "-t", str(a.max_seconds), a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    started = time.time()
    Path(a.out + ".start.json").write_text(json.dumps({"started_epoch": started}), encoding="utf-8")
    print(f"recording started {time.strftime('%H:%M:%S')} -> {a.out}", flush=True)
    while proc.poll() is None:
        if stop.exists():
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
                proc.wait(8)
            except (OSError, subprocess.TimeoutExpired):
                proc.terminate()
            break
        time.sleep(0.5)
    code = proc.wait()
    size = Path(a.out).stat().st_size / 1e6 if Path(a.out).exists() else 0
    print(f"recording stopped after {time.time() - started:.0f} s, ffmpeg exit {code}, {size:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
