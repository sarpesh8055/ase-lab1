"""Two small line charts for the video slides, both read straight from the submitted logs.

    uv run --no-project --with matplotlib python make_charts.py <repo-root> <out-dir>

  context_task1.png  tokens sent per model call in OpenCode session 02 (task1_opencode/conversation/session_02.json)
  context_task2.png  tokens sent per step in our own agent's final run (task2_own_agent/logs/run_03.jsonl)

One data series each, one axis, labels on the first and last point only.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SERIES = "#e1e0d9", "#c3c2b7", "#2a78d6"
plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]


def base(width_px: int, height_px: int):
    fig = plt.figure(figsize=(width_px / 100, height_px / 100), dpi=100, facecolor=SURFACE)
    ax = fig.add_axes((0.06, 0.2, 0.92, 0.66), facecolor=SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(axis="x", labelsize=17, labelcolor=MUTED, length=0, pad=8)
    ax.tick_params(axis="y", labelsize=17, labelcolor=MUTED, length=0, pad=8)
    return fig, ax


def line(ax, xs, ys):
    ax.plot(xs, ys, color=SERIES, linewidth=2.5, solid_capstyle="round", zorder=3)
    ax.scatter([xs[0], xs[-1]], [ys[0], ys[-1]], s=80, color=SERIES, edgecolor=SURFACE, linewidth=2, zorder=4)


def task1(repo: Path, out: Path) -> None:
    data = json.loads((repo / "task1_opencode/conversation/session_02.json").read_text(encoding="utf-8-sig"))
    calls, starts = [], []
    for msg in data["messages"]:
        if msg["info"]["role"] == "user":
            starts.append(len(calls) + 1)
        else:
            tok = msg["info"]["tokens"]
            calls.append((tok["input"] + tok["cache"]["read"]) / 1000)
    xs = list(range(1, len(calls) + 1))
    fig, ax = base(1760, 470)
    line(ax, xs, calls)
    ax.annotate(f"{calls[0]:.1f}k", (xs[0], calls[0]), xytext=(10, -6), textcoords="offset points", fontsize=19,
                color=INK, va="top")
    ax.annotate(f"{calls[-1]:.1f}k", (xs[-1], calls[-1]), xytext=(-6, -14), textcoords="offset points", fontsize=19,
                color=INK, ha="right", va="top")
    ends = starts[1:] + [len(calls) + 1]
    for n, (start, end) in enumerate(zip(starts, ends), 1):
        if n > 1:
            ax.axvline(start - 0.5, color=AXIS, linewidth=1, zorder=1)
        ax.text(start - 0.5 + 0.4, 83, f"Prompt {n}", fontsize=18, color=INK2, va="bottom", fontweight="bold",
                clip_on=False)
        ax.text(start - 0.5 + 0.4 + 6.3, 83.4, f"{end - start} calls", fontsize=16, color=MUTED, va="bottom",
                clip_on=False)
    ax.set_xlim(0.5, len(calls) + 0.5)
    ax.set_ylim(0, 80)
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.set_yticklabels(["0", "20k", "40k", "60k", "80k"])
    ax.set_xticks([1, 10, 20, 30, 40, 50, 60, 70, len(calls)])
    ax.set_xlabel("model call number", fontsize=17, color=MUTED, labelpad=8)
    fig.savefig(out / "context_task1.png", facecolor=SURFACE)
    print(f"context_task1.png: {len(calls)} calls, {calls[0]:.1f}k -> {calls[-1]:.1f}k, prompts start at {starts}")


def task2(repo: Path, out: Path) -> None:
    rows = []
    for raw in (repo / "task2_own_agent/logs/run_03.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    tokens = [r["usage"]["prompt_tokens"] / 1000 for r in rows if r.get("type") == "chat"]
    actions = [r["action"] for r in rows if r.get("event") == "action"]
    feedback_after = next(r["step"] for r in rows if r.get("event") == "human_feedback")
    xs = list(range(1, len(tokens) + 1))
    fig, ax = base(860, 400)
    ax.set_position((0.1, 0.22, 0.86, 0.62))
    line(ax, xs, tokens)
    ax.annotate(f"{tokens[0]:.1f}k", (xs[0], tokens[0]), xytext=(-4, 16), textcoords="offset points", fontsize=18,
                color=INK, ha="center", va="bottom")
    ax.annotate(f"{tokens[-1]:.1f}k", (xs[-1], tokens[-1]), xytext=(-4, -14), textcoords="offset points", fontsize=18,
                color=INK, ha="right", va="top")
    first_write = actions.index("write_site") + 1
    ax.annotate("writes the page", (first_write + 0.5, (tokens[first_write - 1] + tokens[first_write]) / 2),
                xytext=(-14, 4), textcoords="offset points", fontsize=16, color=INK2, ha="right", va="center")
    ax.axvline(feedback_after + 0.5, color=AXIS, linewidth=1, zorder=1)
    ax.text(feedback_after + 0.5 + 0.15, 0.6, "our feedback", fontsize=16, color=INK2, va="bottom")
    ax.set_xlim(0.5, len(tokens) + 0.5)
    ax.set_ylim(0, 15)
    ax.set_yticks([0, 5, 10, 15])
    ax.set_yticklabels(["0", "5k", "10k", "15k"])
    ax.set_xticks(xs)
    ax.set_xlabel("step", fontsize=17, color=MUTED, labelpad=6)
    fig.savefig(out / "context_task2.png", facecolor=SURFACE)
    print(f"context_task2.png: {len(tokens)} steps, {tokens[0] * 1000:.0f} -> {tokens[-1] * 1000:.0f} tokens, "
          f"first write at step {first_write}, feedback after step {feedback_after}")


def main() -> None:
    repo, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    task1(repo, out)
    task2(repo, out)


if __name__ == "__main__":
    main()
