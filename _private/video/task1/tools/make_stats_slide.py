"""Build the Task 1 statistics slide (1920x1080 PNG) from the exported OpenCode session.

    uv run --no-project --with matplotlib python make_stats_slide.py <session_02.json> <out.png>

Every number on the slide is read from the export file, so it can be reproduced
from the submission (task1_opencode/conversation/session_02.json).
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

# Light-surface chart colours (one data series, so one hue; text stays in ink colours).
SURFACE, PAGE = "#fcfcfb", "#f9f9f7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SERIES = "#e1e0d9", "#c3c2b7", "#2a78d6"

plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]


def load(path: Path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    prompts, calls = [], []
    for msg in data["messages"]:
        info = msg["info"]
        if info["role"] == "user":
            prompts.append({"calls": 0, "tools": 0, "failed": 0, "new": 0, "cached": 0, "out": 0,
                            "reasoning": 0, "cost": 0.0, "context": 0, "first_call": len(calls) + 1})
            continue
        tok = info["tokens"]
        context = tok["input"] + tok["cache"]["read"]
        calls.append(context)
        p = prompts[-1]
        p["calls"] += 1
        p["new"] += tok["input"]
        p["cached"] += tok["cache"]["read"]
        p["out"] += tok["output"]
        p["reasoning"] += tok["reasoning"]
        p["cost"] += info.get("cost") or 0
        p["context"] = context
        for part in msg["parts"]:
            if part["type"] == "tool":
                p["tools"] += 1
                p["failed"] += part["state"].get("status") == "error"
    minutes = (data["info"]["time"]["updated"] - data["info"]["time"]["created"]) / 60000
    return prompts, calls, minutes


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    prompts, calls, minutes = load(src)
    total = {k: sum(p[k] for p in prompts) for k in ("calls", "tools", "failed", "new", "cached", "out", "reasoning", "cost")}
    sent = total["new"] + total["cached"]

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=PAGE)
    fig.text(0.04, 0.925, "Task 1, session 02: every model call re-sends the whole conversation",
             fontsize=30, fontweight="bold", color=INK)
    fig.text(0.04, 0.885, f"The context grew from {calls[0] / 1000:.1f}k to {calls[-1] / 1000:.1f}k tokens. "
             f"{total['cached'] / sent:.0%} of everything sent was a cached repeat, which is billed at a tenth of the price.",
             fontsize=17, color=INK2)

    # --- headline numbers -------------------------------------------------------
    tiles = [(f"{len(prompts)}", "prompts from us"), (f"{total['calls']}", "model calls"),
             (f"{total['tools']}", f"tool calls ({total['failed']} failed)"),
             (f"{sent / 1e6:.1f}M", "tokens sent to the model"), (f"${total['cost']:.2f}", "total cost"),
             (f"{minutes:.0f} min", "start to finish")]
    x0, width, gap = 0.04, 0.143, 0.0124
    for i, (value, label) in enumerate(tiles):
        x = x0 + i * (width + gap)
        fig.add_artist(FancyBboxPatch((x, 0.735), width, 0.115, boxstyle="round,pad=0,rounding_size=0.008",
                                      transform=fig.transFigure, facecolor=SURFACE, edgecolor="#e6e5df", linewidth=1))
        fig.text(x + 0.012, 0.785, value, fontsize=34, fontweight="bold", color=INK)
        fig.text(x + 0.012, 0.752, label, fontsize=15, color=INK2)

    # --- the chart: one series, one axis -----------------------------------------
    ax = fig.add_axes((0.065, 0.35, 0.895, 0.295), facecolor=SURFACE)
    xs = list(range(1, len(calls) + 1))
    ax.plot(xs, [c / 1000 for c in calls], color=SERIES, linewidth=2, solid_capstyle="round", zorder=3)
    ax.scatter([xs[0], xs[-1]], [calls[0] / 1000, calls[-1] / 1000], s=64, color=SERIES, edgecolor=SURFACE,
               linewidth=2, zorder=4)
    ax.annotate(f"{calls[0] / 1000:.1f}k", (xs[0], calls[0] / 1000), xytext=(8, -4), textcoords="offset points",
                fontsize=15, color=INK, va="top")
    ax.annotate(f"{calls[-1] / 1000:.1f}k", (xs[-1], calls[-1] / 1000), xytext=(-6, -12), textcoords="offset points",
                fontsize=15, color=INK, ha="right", va="top")
    top = 80
    for n, p in enumerate(prompts, 1):
        start = p["first_call"]
        if n > 1:
            ax.axvline(start - 0.5, color=AXIS, linewidth=1, zorder=1)
        # prompt names sit in a band above the plot, so they can never collide with the line
        ax.text(start - 0.5 + 0.4, top + 2.5, f"Prompt {n}", fontsize=15, color=INK2, va="bottom",
                fontweight="bold", clip_on=False)
        ax.text(start - 0.5 + 0.4 + 4.6, top + 2.9, f"{p['calls']} calls", fontsize=13, color=MUTED, va="bottom",
                clip_on=False)
    ax.set_xlim(0.5, len(calls) + 0.5)
    ax.set_ylim(0, top)
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.set_yticklabels(["0", "20k", "40k", "60k", "80k"], fontsize=14, color=MUTED)
    ax.set_xticks([1, 10, 20, 30, 40, 50, 60, 70, len(calls)])
    ax.tick_params(axis="x", labelsize=14, labelcolor=MUTED, length=0, pad=8)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.set_xlabel("model call number", fontsize=14, color=MUTED, labelpad=8)
    ax.set_title("Tokens sent to the model on each call (new input + cached input)", fontsize=17, color=INK,
                 loc="left", pad=40, fontweight="bold")

    # --- the same numbers as a table ---------------------------------------------
    cols = [("", 0.04, "left"), ("model calls", 0.275, "right"), ("tool calls", 0.375, "right"),
            ("failed", 0.445, "right"), ("new input", 0.555, "right"), ("cached input", 0.675, "right"),
            ("output", 0.765, "right"), ("reasoning", 0.862, "right"), ("cost", 0.955, "right")]
    y = 0.243
    for name, x, align in cols:
        fig.text(x, y, name, fontsize=14, color=MUTED, ha=align)
    fig.add_artist(Line2D([0.04, 0.955], [y - 0.012, y - 0.012], color=AXIS, linewidth=1, transform=fig.transFigure))
    labels = ["Prompt 1: build the site for all five", "Prompt 2: our review, six problems",
              "Prompt 3: false claim, fix the cause", "Prompt 4: interests in full"]
    rows = [(labels[i] if i < len(labels) else f"Prompt {i + 1}", p) for i, p in enumerate(prompts)] + [("Total", total)]
    for i, (label, p) in enumerate(rows):
        yy = y - 0.042 - i * 0.036
        bold = "bold" if label == "Total" else "normal"
        values = [label, f"{p['calls']}", f"{p['tools']}", f"{p['failed']}", f"{p['new']:,}", f"{p['cached']:,}",
                  f"{p['out']:,}", f"{p['reasoning']:,}", f"${p['cost']:.4f}"]
        for (name, x, align), value in zip(cols, values):
            fig.text(x, yy, value, fontsize=15, color=INK if (name == "" or label == "Total") else INK2,
                     ha=align, fontweight=bold)
        if label == "Total":
            fig.add_artist(Line2D([0.04, 0.955], [yy + 0.027, yy + 0.027], color=GRID, linewidth=1,
                                  transform=fig.transFigure))
    fig.text(0.04, 0.014, f"Source: task1_opencode/conversation/{src.name} (opencode export). Model: GPT-6 Luna via the UPB AI Gateway. "
             "Prices: $0.10 per 1M new input tokens, $0.01 cached, $0.50 output.", fontsize=12, color=MUTED)
    fig.savefig(out, facecolor=PAGE)
    print(f"{out}  prompts={len(prompts)} calls={total['calls']} sent={sent:,} cost=${total['cost']:.4f}")


if __name__ == "__main__":
    main()
