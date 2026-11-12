# Task 1 video material (private: not in git, not in the ZIP)

Made on Nov 12 from the real session 02. Every recording shows one window only, so nothing else from the
screen is in it. No sound. Size: 1382 × 816 (the lab asks for at least 720p).

## What the lab wants in the Task 1 part (about 1:30), and the file for it

| The lab asks for | Use this |
|---|---|
| Screenshots: desktop + mobile, day + night | `screenshots/four_views_slide_cards.png` (all four on one slide) or the single files next to it |
| Session statistics: prompts, tokens, cost | `stats_slide_session_02.png` |
| One moment where the agent went wrong, and how we steered it back | `stills/still_2…`, `still_3…`, `still_4…` or `clips/clip_3…` and `clip_4…` |
| Intro: a screenshot of the website | `screenshots/desktop_day_cards.png` |

## Screenshots (`screenshots/`)

- `desktop_day.png`, `desktop_night.png`, `phone_day.png`, `phone_night.png`: the top of the page
- `…_cards.png`: scrolled to the games and the member cards (better for a slide, the pictures are visible)
- `…_full.png`: the whole page in one tall image
- `four_views_slide_cards.png`, `four_views_slide_top.png`: 1920 × 1080 slides with all four views

Desktop is 1440 × 900. Phone is 390 × 844 at double sharpness. Night mode was switched on with the page's own button.

## Recordings

| File | Length | What it shows |
|---|---|---|
| `opencode_session_02_full.mp4` | 22:36 | The whole OpenCode session in real time, from the first prompt to the last checks |
| `opencode_session_02_timelapse_30x.mp4` | 0:45 | The same, 30 times faster |
| `site_tour_desktop.mp4` | 0:55 | The finished site: both games, scroll through all five cards and the shared view, day → night → day |
| `site_tour_phone.mp4` | 1:01 | The same in a phone-width window |

The full recording ends a few seconds before the agent's last message. That last message is in
`stills/still_8_final_message_and_cost.png`.

## Where things happen in `opencode_session_02_full.mp4`

| Time | What happens |
|---|---|
| 0:10 | Prompt 1 is typed, sent at 0:16 |
| 0:42 | First permission question (edit the site file). Many more follow, each waits about 3 seconds |
| 1:40 | It asks to run `embed_images.py`, then the checker: 7 of 7 at about 1:55 |
| 2:00 | It runs the stricter `--full` check on its own and rewires the toggle to pass it |
| 5:01 | Prompt 2: the six problems we found by looking at the page |
| 5:14, 6:44, 8:00 | Search fails: the line with an embedded picture is too long for the search tool |
| 7:12 | **Patch fails** on a picture line (`clip_3`, `still_2`) |
| 12:32 | **It reports "Removed lazy loading from the embedded portraits". Not true** (`still_3`) |
| 14:24 | Prompt 3: we point out the false claim and tell it to keep a source file with placeholders (`clip_4`) |
| 14:33 | It admits it: "I treated the runtime workaround as proof" (`still_4`) |
| 17:19 | It wants to edit the course's `embed_images.py`. **We reject** at 17:31 (`clip_5`, `still_5`, `still_6`) |
| 19:25 | It lists what it verified and how |
| 21:20 | Prompt 4: interests in full |
| 22:30 | Final checks pass (`clip_6`, `still_7`) |

`session_02_timeline.jsonl` has every prompt and every permission question with its clock time.

## Clips (`clips/`, real time, cut from the full recording)

1. `clip_1_first_prompt_typed_and_sent.mp4` (0:46)
2. `clip_2_asks_permission_then_checker_passes.mp4` (0:32)
3. `clip_3_patch_fails_on_embedded_picture.mp4` (0:22)
4. `clip_4_false_claim_then_our_correction.mp4` (0:34)
5. `clip_5_we_reject_an_edit.mp4` (0:28)
6. `clip_6_final_checks_pass.mp4` (0:26)

## Numbers (all from `task1_opencode/conversation/session_02.json`)

- 4 prompts, 81 model calls, 103 tool calls (7 failed), 22 minutes, $0.0699
- Tokens sent to the model: 4,107,006 in total (70,952 new + 4,036,054 cached). Output 22,824, reasoning 22,146
- The conversation grew from 11,015 to 70,712 tokens
- `opencode stats` for the project says $0.07, 81.9K input, 23.0K output, 4.1M cache read. That includes the hello-world session

To rebuild the statistics slide:
`uv run --no-project --with matplotlib python tools/make_stats_slide.py ../../../task1_opencode/conversation/session_02.json stats_slide_session_02.png`

## Tools (`tools/`)

The scripts that drove OpenCode and made these files, kept in case another session is needed:
`oc.py` (types prompts into OpenCode and answers permission questions through its `--port`), `rec.py` (records one
window), `win.py`, `screen.py`, `site.py` (screenshots and checks), `tour.py` (site walk-through), `four_up.py`,
`content_check.py` (profile text vs. page text), `export_md.py` (readable copy of the export), `html_view.py`,
`make_stats_slide.py`. `tools/prompts/` has the four prompts exactly as sent.
