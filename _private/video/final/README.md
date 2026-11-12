# The Lab 1 video: what is here and how to finish it

This folder is private (not in git, not in the ZIP). The video is uploaded to PANDA on its own.

## What exists

| File | What it is |
|---|---|
| `out/…_lab1_video_NO_VOICE.mp4` | The video, 9:42, 1920 × 1080, all six parts in the order the lab asks for. Silent |
| `out/…_lab1_recording_guide.mp4` | The same video with the script and a countdown under it. For rehearsing |
| `out/…_record_part1_….mp4` … `part6` | One clip per speaker: a 3-2-1 countdown, then that part with the script under it |
| `VOICEOVER_SCRIPT.md` | The script: who speaks when, and the text for every slide |
| `out/…_lab1_video.srt` | The script as subtitles |
| `slides/s01.png` … `s20.png` | The 20 slides as pictures |
| `team.json` | The facts only the team knows. **Fill this in first** |
| `storyboard.json` | The voiceover text per slide. The video is timed from it |
| `deck/` | The slides as HTML |

Files start with `DRAFT_` as long as `team.json` has open `TODO` entries.

## Three steps to the final file

**1. Fill in `team.json`.** Group number, `file_prefix` (for example `group-07`), what each person did, which AI
assistants were used for the first version of Tasks 2–4, the numbers of session 01, and who speaks which part. Then:

```
uv run --no-project --with playwright python tools/build_video.py
```

That takes about three minutes and rebuilds everything. The yellow boxes on the slides are gone when nothing starts with `TODO`.

**2. Record the voices.** Every speaker opens their `record_partN` clip, starts a voice recorder (phone or PC)
at the same moment, and starts speaking when the first slide appears. The white line under the video is the sentence
to say now. The yellow line counts down to the next slide. Save the recordings as `voice/part1.m4a` … `voice/part6.m4a`
(any audio format works).

**3. Put the voices on the video.**

```
python tools/add_voiceover.py
```

It cuts the 3-second countdown off each recording, brings all voices to the same loudness, writes
`out/<file_prefix>_lab1_video.mp4`, and checks the lab's rules: MP4, at most 10:00, at least 720p, has audio,
a voice for every part. It prints `READY TO SUBMIT` when all of them hold.

If you would rather use a video editor: import the `NO_VOICE` file, record the narration on top, and export as MP4 at 1080p.
Do not change the length.

## Changing the text or the timing

- Change a sentence in `storyboard.json` and run step 1 again. A slide stays on screen for
  `words / words_per_second + pause` seconds, so the video follows the text.
- The video must stay under 10:00. The build stops if it gets within 5 seconds of that.
- `words_per_second` in `team.json` is 2.4 (144 words per minute). Slower speakers: shorten the text rather than lowering this.
- To change what a slide shows, edit `deck/slides_a.html` (parts 1–3) or `deck/slides_b.html` (parts 4–6).

## Where every number comes from

| Part | Source in the submission |
|---|---|
| Task 1 | `task1_opencode/conversation/session_02.json` (tokens, calls, cost); the checker; `session_stats.md` |
| Task 2 | `task2_own_agent/logs/run_03.jsonl` (steps, searches, tokens, step 12); `rag.py --eval` (14 and 18 of 18) |
| Task 3 | `task3_rag/results/metrics_*.json`, `judge_*.jsonl`, `weight_sweep.json`, `failures_R5_hybrid_hyde.md`; latencies from the README |
| Task 4 | `task4_tools/logs/trace.jsonl`, `trace_mock.jsonl`, `llm_real.jsonl`, `final.diff`, line numbers in `tools.py` |

The charts are rebuilt with `uv run --no-project --with matplotlib python tools/make_charts.py ../../.. assets`.
