"""Put the recorded voices onto the silent video and check the result against the lab's rules.

    python tools/add_voiceover.py [--voice voice] [--strict] [--no-normalise]

Put the recordings into the folder `voice/`. Any common audio or video format works
(m4a, mp3, wav, ogg, webm, mp4 ...). Two ways to name them:

    part1 ... part6     one file per part; it starts when that part starts
    full                one file for the whole video; it starts at 0:00

A recording that is longer than its part runs into the next part. The script
tells you by how many seconds. With --strict it stops instead of writing a file.

The picture is copied unchanged. Every voice file is brought to the same loudness
(unless --no-normalise), so five different microphones sound alike.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

FINAL = Path(__file__).resolve().parent.parent
LIMIT_S = 600


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    data = json.loads(out or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {"duration": float(data.get("format", {}).get("duration", 0) or 0),
            "audio": any(s.get("codec_type") == "audio" for s in streams),
            "width": video.get("width"), "height": video.get("height")}


def find(folder: Path, stem: str):
    hits = sorted(p for p in folder.glob(f"{stem}.*") if p.is_file())
    return hits[0] if hits else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=str(FINAL / "voice"))
    ap.add_argument("--video", help="the silent video (default: the newest *_NO_VOICE.mp4 in out/)")
    ap.add_argument("--out", help="output file (default: out/<prefix>_lab1_video.mp4)")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-normalise", action="store_true")
    ap.add_argument("--lead", type=float, default=3.0,
                    help="seconds to cut from the start of every part recording: the 3-2-1 countdown of the "
                         "record_partN clips (default 3; use 0 if you recorded without the countdown)")
    a = ap.parse_args()

    timeline = json.loads((FINAL / "build" / "timeline.json").read_text(encoding="utf-8"))
    cfg = json.loads((FINAL / "team.json").read_text(encoding="utf-8"))
    total = timeline["total_seconds"]
    silent = Path(a.video) if a.video else max((FINAL / "out").glob("*_NO_VOICE.mp4"), key=lambda p: p.stat().st_mtime)
    draft = silent.name.startswith("DRAFT_")
    out = Path(a.out) if a.out else FINAL / "out" / f"{'DRAFT_' if draft else ''}{cfg['file_prefix']}_lab1_video.mp4"
    folder = Path(a.voice)

    tracks, problems = [], []
    full = find(folder, "full")
    if full:
        tracks.append((full, 0.0, total, "whole video", 0.0))
    else:
        for part in timeline["parts"]:
            file = find(folder, f"part{part['part']}")
            label = f"part {part['part']} ({part['name']}, {part['speaker']})"
            if not file:
                problems.append(f"missing: {folder.name}/part{part['part']}.*  for {label}")
                continue
            tracks.append((file, part["start"], part["end"] - part["start"], label, a.lead))
    if not tracks:
        raise SystemExit(f"No recordings found in {folder}. Expected part1 ... part6, or full.")

    print(f"silent video: {silent.name} ({total:.1f} s)")
    for file, start, slot, label, lead in tracks:
        length = max(0.0, probe(file)["duration"] - lead)
        note = "ok"
        if length > slot + 0.4:
            note = f"TOO LONG by {length - slot:.1f} s, it runs into the next part"
            problems.append(f"{file.name}: {note}")
        elif length < slot * 0.6:
            note = f"short: {slot - length:.0f} s of silence at the end"
        print(f"  {file.name:22} {label:44} starts {start:6.1f} s, slot {slot:5.1f} s, recording {length:5.1f} s  {note}")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
        if a.strict:
            raise SystemExit("stopped because of --strict")

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent)]
    chain, labels = [], []
    for i, (file, start, _slot, _label, lead) in enumerate(tracks, 1):
        cmd += ["-i", str(file)]
        loud = "" if a.no_normalise else "loudnorm=I=-16:TP=-1.5:LRA=11,"
        cut = f"atrim=start={lead:.2f},asetpts=PTS-STARTPTS," if lead > 0 else ""
        chain.append(f"[{i}:a]{cut}{loud}aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"adelay={int(start * 1000)}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    chain.append(f"{''.join(labels)}amix=inputs={len(tracks)}:normalize=0:duration=longest,apad,atrim=0:{total:.2f}[a]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        sys.stderr.write(done.stderr[-2500:])
        raise SystemExit("ffmpeg could not write the video")

    info = probe(out)
    checks = [("MP4 file", out.suffix.lower() == ".mp4"),
              (f"at most 10:00 (is {int(info['duration'] // 60)}:{int(info['duration'] % 60):02d})", info["duration"] <= LIMIT_S),
              (f"at least 720p (is {info['width']}x{info['height']})", (info["height"] or 0) >= 720),
              ("has audio", info["audio"]),
              ("a voice for every part", not any(p.startswith("missing") for p in problems)),
              ("no recording runs over its part", not any("TOO LONG" in p for p in problems)),
              ("no open TODO in team.json", not draft)]
    print(f"\nwrote {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    for label, ok in checks:
        print(f"  [{'ok' if ok else 'NO'}] {label}")
    print("READY TO SUBMIT" if all(ok for _, ok in checks) else "NOT READY YET: fix the lines marked NO")


if __name__ == "__main__":
    main()
