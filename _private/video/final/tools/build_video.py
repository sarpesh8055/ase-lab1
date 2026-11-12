"""Build the Lab 1 video from the slides and the storyboard.

    uv run --no-project --with playwright python tools/build_video.py [--skip-render] [--skip-guide]

Reads   team.json        group name, who did what, speakers, speaking pace
        storyboard.json  one entry per slide with the voiceover text
        deck/*.html      the slides (1920 x 1080 each)
Writes  slides/sNN.png                         one picture per slide
        out/<name>_NO_VOICE.mp4                the video without a voice (silent audio track)
        out/<name>_recording_guide.mp4         the same video with the script and a countdown under it
        out/<name>.srt                         the script as subtitles
        VOICEOVER_SCRIPT.md                    the script with times, per speaker
        build/timeline.json                    start and end of every slide and part (used by add_voiceover.py)

Each slide stays on screen for (words / words_per_second + pause) seconds, so the video
always matches the script. Change a text, run this again, and both are in step.
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

FINAL = Path(__file__).resolve().parent.parent
DECK, SLIDES, BUILD, OUT = FINAL / "deck", FINAL / "slides", FINAL / "build", FINAL / "out"
W, H, FPS = 1920, 1080, 30
LIMIT_S = 600  # the lab grades nothing after 10:00


def is_todo(value: str) -> bool:
    """Open item: left empty, or still starting with TODO."""
    return not value.strip() or value.strip().upper().startswith("TODO")


def mark(value: str) -> str:
    """Slide text for a team.json value: an empty value becomes an empty box to fill in later,
    a TODO value a yellow box so nobody overlooks it."""
    if not value.strip():
        return '<span class="blank"></span>'
    text = html.escape(value)
    return f'<span class="todo">{text}</span>' if is_todo(value) else text


def run(cmd, cwd=None) -> None:
    proc = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-3000:])
        raise SystemExit(f"ffmpeg failed: {' '.join(str(c) for c in cmd[:6])} …")


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


# ---------------------------------------------------------------- slides -> PNG
def render_slides(cfg: dict, scenes: list) -> dict:
    from playwright.sync_api import sync_playwright

    group = cfg["group"]
    subs = {
        "[[group_plain]]": "Group ??" if is_todo(group) else html.escape(group),
        "[[group]]": mark("Group ?? (fill in team.json)") if is_todo(group) else html.escape(group),
        "[[ai_tools]]": mark(cfg["ai_tools_tasks_2_to_4"]),
        "[[s01_stats]]": mark(cfg["session01_tokens_and_cost"]),
    }
    for name, did in cfg["who_did_what"].items():
        subs[f"[[who:{name}]]"] = mark(did)
    SLIDES.mkdir(exist_ok=True)
    clips = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for deck in sorted({s["deck"] for s in scenes}):
            text = (DECK / deck).read_text(encoding="utf-8")
            for key, value in subs.items():
                text = text.replace(key, value)
            left = re.findall(r"\[\[[^\]]+\]\]", text)
            if left:
                raise SystemExit(f"{deck}: unknown placeholders {sorted(set(left))}")
            rendered = DECK / f"_render_{deck}"
            rendered.write_text(text, encoding="utf-8")
            page.goto(rendered.as_uri())
            page.wait_for_load_state("networkidle")
            broken = page.evaluate("Array.from(document.images).filter(i => !i.complete || !i.naturalWidth).map(i => i.getAttribute('src'))")
            if broken:
                raise SystemExit(f"{deck}: pictures that did not load: {broken}")
            page.wait_for_timeout(300)
            for scene in (s for s in scenes if s["deck"] == deck):
                el = page.locator(f"#{scene['id']}")
                box = el.bounding_box()
                if not box or round(box["width"]) != W or round(box["height"]) != H:
                    raise SystemExit(f"{scene['id']}: slide is {box}, expected {W}x{H}")
                overflow = page.evaluate(
                    """(id) => { const s = document.getElementById(id); const r = s.getBoundingClientRect();
                         return [...s.querySelectorAll('*')].filter(e => { const b = e.getBoundingClientRect();
                           return b.width > 0 && (b.bottom > r.bottom - 20 || b.right > r.right - 20) && !e.closest('svg'); })
                           .slice(0, 3).map(e => e.tagName + ':' + (e.textContent || '').trim().slice(0, 40)); }""", scene["id"])
                if overflow:
                    print(f"  WARNING {scene['id']}: content reaches the slide edge: {overflow}")
                el.screenshot(path=str(SLIDES / f"{scene['id']}.png"))
                clips[scene["id"]] = page.evaluate(
                    """(id) => { const s = document.getElementById(id); const r0 = s.getBoundingClientRect();
                         return [...s.querySelectorAll('[data-clip]')].map(e => { const r = e.getBoundingClientRect();
                           return {clip: e.dataset.clip, ss: Number(e.dataset.ss || 0), crop: e.dataset.crop || '',
                                   x: Math.round(r.left - r0.left) + 1, y: Math.round(r.top - r0.top) + 1,
                                   w: Math.floor((r.width - 2) / 2) * 2, h: Math.floor((r.height - 2) / 2) * 2}; }); }""",
                    scene["id"])
            rendered.unlink()
        browser.close()
    print(f"rendered {len(scenes)} slides -> {SLIDES}")
    return clips


# ---------------------------------------------------------------- timing
def spoken(cfg: dict, scene: dict) -> str:
    group = cfg["group"]
    return scene["say"].replace("{group}", "group [number]" if is_todo(group) else group[0].lower() + group[1:])


def plan(cfg: dict, board: dict) -> list:
    wps, pause = float(cfg["words_per_second"]), float(cfg["pause_per_slide_seconds"])
    t = 0.0
    rows = []
    for number, scene in enumerate(board["scenes"], 1):
        say = spoken(cfg, scene)
        words = len(say.split())
        seconds = float(scene["seconds"]) if "seconds" in scene else max(6.0, round(words / wps + pause, 1))
        rows.append({**scene, "n": number, "say": say, "words": words, "seconds": seconds, "start": round(t, 2),
                     "end": round(t + seconds, 2), "speak_until": round(t + seconds - pause, 2),
                     "speaker": cfg["speakers"][str(scene["part"])], "part_name": board["parts"][str(scene["part"])]})
        t += seconds
    return rows


def sentences(row: dict) -> list:
    """Split the text of one slide into sentences and give each a time slice by its word count."""
    parts = [p for p in re.split(r"(?<=[.!?\]])\s+", row["say"]) if p.strip()]
    total = sum(len(p.split()) for p in parts)
    span = row["speak_until"] - row["start"]
    out, t = [], row["start"] + 0.3
    for part in parts:
        length = span * len(part.split()) / total
        out.append((round(t, 2), round(min(t + length, row["speak_until"] + 0.3), 2), part))
        t += length
    return out


# ---------------------------------------------------------------- video
def make_segments(rows: list, clips: dict) -> None:
    BUILD.mkdir(exist_ok=True)
    for row in rows:
        png, seg, dur = SLIDES / f"{row['id']}.png", BUILD / f"seg_{row['id']}.mp4", row["seconds"]
        common = ["-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                  "-r", str(FPS), "-video_track_timescale", "30000", "-an", seg]
        targets = clips.get(row["id"]) or []
        if not targets:
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png,
                 "-vf", "format=yuv420p", "-tune", "stillimage", *common])
            continue
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png]
        chain, last = [], "[0:v]"
        for i, target in enumerate(targets, 1):
            clip = (DECK / target["clip"]).resolve()
            if not clip.exists():
                raise SystemExit(f"{row['id']}: clip not found: {clip}")
            cmd += ["-ss", str(target["ss"]), "-i", clip]
            crop = f"crop={target['crop']}," if target["crop"] else ""
            chain.append(f"[{i}:v]fps={FPS},{crop}scale={target['w']}:{target['h']}:force_original_aspect_ratio=increase:"
                         f"flags=lanczos,crop={target['w']}:{target['h']}:0:0,tpad=stop_mode=clone:stop_duration={dur:.0f},"
                         f"setsar=1[c{i}]")
            chain.append(f"{last}[c{i}]overlay={target['x']}:{target['y']}:eof_action=repeat[o{i}]")
            last = f"[o{i}]"
        chain.append(f"{last}format=yuv420p[v]")
        run(cmd + ["-filter_complex", ";".join(chain), "-map", "[v]", *common])
    print(f"encoded {len(rows)} segments")


def join(rows: list, clean: Path) -> float:
    total = rows[-1]["end"]
    listing = BUILD / "segments.txt"
    listing.write_text("".join(f"file 'seg_{r['id']}.mp4'\n" for r in rows), encoding="utf-8")
    # a thin bar along the bottom edge shows how far the video is
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing.name,
         "-f", "lavfi", "-i", f"color=c=0x2a78d6:s={W}x5:r={FPS}", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-filter_complex", f"[0:v][1:v]overlay=x='-w+w*t/{total:.2f}':y=H-5:shortest=1,format=yuv420p[v]",
         "-map", "[v]", "-map", "2:a", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", clean], cwd=BUILD)
    return total


def ass_time(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def make_guide(rows: list, clean: Path, guide: Path) -> None:
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1340\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Say,Segoe UI,42,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,60,60,1150,1\n"
        "Style: Meta,Segoe UI,28,&H0070E5FF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,7,60,60,1096,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = []
    for row in rows:
        for start, end, text in sentences(row):
            safe = text.replace("{", "(").replace("}", ")")
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Say,,0,0,0,,{safe}")
        second = row["start"]
        while second < row["end"] - 0.01:
            nxt = min(second + 1, row["end"])
            left = row["end"] - second
            lines.append(f"Dialogue: 1,{ass_time(second)},{ass_time(nxt)},Meta,,0,0,0,,Part {row['part']}: {row['part_name']}"
                         f"     Speaker: {row['speaker']}     Slide {row['n']} of {len(rows)}     next slide in {left:.0f} s")
            second = nxt
    (BUILD / "guide.ass").write_text(head + "\n".join(lines) + "\n", encoding="utf-8-sig")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", clean, "-vf",
         "pad=1920:1340:0:0:color=0x111118,subtitles=guide.ass", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-an", "-movflags", "+faststart", guide], cwd=BUILD)


LEAD_S = 3  # seconds of countdown before each speaker's clip starts; add_voiceover.py cuts the same amount


def make_part_guides(rows: list, guide: Path, prefix: str) -> list:
    """One clip per part for the speaker to record against: a 3-2-1 countdown, then that part of the guide."""
    made = []
    for part in sorted({r["part"] for r in rows}):
        items = [r for r in rows if r["part"] == part]
        start, end, speaker = items[0]["start"], items[-1]["end"], items[0]["speaker"]
        ass = BUILD / f"pre_part{part}.ass"
        head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1340\nWrapStyle: 0\n\n[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                "MarginR, MarginV, Encoding\n"
                "Style: Big,Segoe UI,300,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,60,60,60,1\n"
                "Style: Top,Segoe UI,54,&H0070E5FF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,8,60,60,150,1\n\n"
                "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        events = [f"Dialogue: 0,{ass_time(0)},{ass_time(LEAD_S)},Top,,0,0,0,,Part {part}: {items[0]['part_name']}   "
                  f"Speaker: {speaker}\\NStart your voice recorder now. Speak when the slide appears."]
        events += [f"Dialogue: 0,{ass_time(i)},{ass_time(i + 1)},Big,,0,0,0,,{LEAD_S - i}" for i in range(LEAD_S)]
        ass.write_text(head + "\n".join(events) + "\n", encoding="utf-8-sig")
        safe = re.sub(r"[^A-Za-z0-9]+", "", speaker) or "speaker"
        out = OUT / f"{prefix}_record_part{part}_{safe}.mp4"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c=0x111118:s=1920x1340:r={FPS}:d={LEAD_S}",
             "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", guide,
             "-filter_complex", f"[0:v]subtitles={ass.name},format=yuv420p[pre];[1:v]fps={FPS},format=yuv420p[main];"
                                f"[pre][main]concat=n=2:v=1:a=0[v]",
             "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an", "-movflags", "+faststart", out],
            cwd=BUILD)
        made.append(out)
    return made


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_texts(cfg: dict, board: dict, rows: list, total: float, names: dict, todos: list) -> None:
    srt = []
    for i, (start, end, text) in enumerate((s for row in rows for s in sentences(row)), 1):
        srt.append(f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
    names["srt"].write_text("\n".join(srt), encoding="utf-8")

    parts = {}
    for row in rows:
        parts.setdefault(row["part"], []).append(row)
    timeline = {"total_seconds": total, "parts": [], "slides": [
        {k: row[k] for k in ("id", "n", "part", "start", "end", "seconds", "words", "speaker", "title")} for row in rows]}
    md = ["# Voiceover script, Lab 1 video", "",
          "> **This file is generated.** `tools/build_video.py` writes it again on every build, so anything typed in here is lost.",
          "> To change a sentence, edit `storyboard.json`. To change names or facts, edit `team.json`. Then build again.", "",
          f"Video length: **{clock(total)}** ({total:.0f} s). The limit is 10:00, and nothing after it is graded.",
          f"Speaking pace assumed: {float(cfg['words_per_second']) * 60:.0f} words per minute, plus "
          f"{cfg['pause_per_slide_seconds']} s of breathing room on every slide.",
          f"Words in total: {sum(r['words'] for r in rows)}.", ""]
    if todos:
        md += ["> **Not final yet.** These entries in `team.json` are still open, and they show up in yellow on the slides:"]
        md += [f"> - {t}" for t in todos] + [""]
    md += ["## Who speaks when", "", "| Part | Speaker | From | To | Length | Words |", "|---|---|---|---|---|---|"]
    for part, items in parts.items():
        start, end = items[0]["start"], items[-1]["end"]
        timeline["parts"].append({"part": part, "name": board["parts"][str(part)], "speaker": items[0]["speaker"],
                                  "start": start, "end": end})
        md.append(f"| {part}. {board['parts'][str(part)]} | {items[0]['speaker']} | {clock(start)} | {clock(end)} | "
                  f"{clock(end - start)} | {sum(i['words'] for i in items)} |")
    md += ["", "The speaker names come from `team.json` (`speakers`). Change them there; the slides do not show them.", ""]
    for part, items in parts.items():
        md += [f"## {part}. {board['parts'][str(part)]} · {items[0]['speaker']} · {clock(items[0]['start'])} to "
               f"{clock(items[-1]['end'])}", ""]
        for row in items:
            md += [f"**Slide {row['n']}: {row['title']}** · {clock(row['start'])} to {clock(row['end'])} · "
                   f"{row['seconds']:.0f} s · {row['words']} words", "", f"> {row['say']}", ""]
            if row.get("check"):
                md += [f"*Before you record this:* {row['check']}", ""]
    names["script"].write_text("\n".join(md), encoding="utf-8")
    (BUILD / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-render", action="store_true", help="reuse the slide pictures from the last run")
    ap.add_argument("--skip-guide", action="store_true", help="do not build the recording guide")
    ap.add_argument("--plan-only", action="store_true", help="only print the timing")
    ap.add_argument("--part-guides-only", action="store_true", help="only cut the per-speaker recording clips")
    ap.add_argument("--texts-only", action="store_true",
                    help="only rewrite the script, the subtitles and the timeline (no video work; use it after "
                         "changing a note, not after changing a sentence, because sentences change the slide times)")
    a = ap.parse_args()
    cfg = json.loads((FINAL / "team.json").read_text(encoding="utf-8"))
    board = json.loads((FINAL / "storyboard.json").read_text(encoding="utf-8"))
    rows = plan(cfg, board)
    total = rows[-1]["end"]
    todos = [f"{key}: {value or '(empty)'}" for key, value in [("group", cfg["group"]),
             ("session01_tokens_and_cost", cfg["session01_tokens_and_cost"]),
             ("ai_tools_tasks_2_to_4", cfg["ai_tools_tasks_2_to_4"]),
             *[(f"who_did_what.{n}", v) for n, v in cfg["who_did_what"].items()]] if is_todo(value)]
    for part in sorted({r["part"] for r in rows}):
        items = [r for r in rows if r["part"] == part]
        print(f"part {part} {items[0]['part_name']:24} {clock(items[0]['start'])}-{clock(items[-1]['end'])}  "
              f"{items[-1]['end'] - items[0]['start']:5.0f} s  {sum(i['words'] for i in items):4} words  ({items[0]['speaker']})")
    print(f"TOTAL {clock(total)} ({total:.1f} s), {sum(r['words'] for r in rows)} words, {len(rows)} slides")
    if total > LIMIT_S - 5:
        raise SystemExit(f"too long: {total:.0f} s. Shorten the text in storyboard.json or raise words_per_second.")
    if a.plan_only:
        return
    OUT.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    prefix = ("DRAFT_" if todos else "") + cfg["file_prefix"]
    names = {"clean": OUT / f"{prefix}_lab1_video_NO_VOICE.mp4", "guide": OUT / f"{prefix}_lab1_recording_guide.mp4",
             "srt": OUT / f"{prefix}_lab1_video.srt", "script": FINAL / "VOICEOVER_SCRIPT.md"}
    part_clips = []
    if a.texts_only:
        write_texts(cfg, board, rows, total, names, todos)
    elif a.part_guides_only:
        part_clips = make_part_guides(rows, names["guide"], prefix)
    else:
        if a.skip_render:
            clips = json.loads((BUILD / "clips.json").read_text(encoding="utf-8"))
        else:
            clips = render_slides(cfg, board["scenes"])
            (BUILD / "clips.json").write_text(json.dumps(clips, indent=1), encoding="utf-8")
        make_segments(rows, clips)
        fresh = BUILD / "_new_video.mp4"
        join(rows, fresh)
        # Only now, with the new video finished, remove what this script made last time, so a build
        # that fails (no Edge, no ffmpeg) leaves the old files alone. A video that already has voices
        # on it is never touched. Removing also clears DRAFT_ names once team.json is complete.
        for old in [*OUT.glob("*_lab1_video_NO_VOICE.mp4"), *OUT.glob("*_lab1_recording_guide.mp4"),
                    *OUT.glob("*_record_part*.mp4"), *OUT.glob("*_lab1_video.srt")]:
            try:
                old.unlink()
            except PermissionError:
                raise SystemExit(f"Cannot replace {old.name}: it is open in another program. Close it and build again.")
        fresh.replace(names["clean"])
        write_texts(cfg, board, rows, total, names, todos)
        if not a.skip_guide:
            make_guide(rows, names["clean"], names["guide"])
            part_clips = make_part_guides(rows, names["guide"], prefix)
    print("wrote:")
    for path in [*names.values(), *part_clips]:
        if path.exists():
            print(f"  {path}  ({path.stat().st_size / 1e6:.1f} MB)")
    if todos:
        print("STILL OPEN in team.json (yellow on the slides, file names start with DRAFT_):")
        for t in todos:
            print("  -", t)


if __name__ == "__main__":
    main()
