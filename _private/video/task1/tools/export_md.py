"""Turn an `opencode export` JSON file into (1) a readable Markdown transcript in the same
layout OpenCode's own /export uses, and (2) per-prompt statistics.

    python export_md.py <session.json> <out.md> <stats.json>

Nothing is summarised or left out except embedded base64 picture data, which is
replaced by a short "<N KB of base64 cut>" marker so the file stays readable.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

B64 = re.compile(r"(data:image/[\w.+-]+;base64,)[A-Za-z0-9+/=\\]{200,}")


def cut(text: str) -> str:
    return B64.sub(lambda m: f"{m.group(1)}<{len(m.group(0)) // 1024} KB of base64 cut>", text)


def stamp(ms: int) -> str:
    d = dt.datetime.fromtimestamp(ms / 1000)
    return f"{d.month}/{d.day}/{d.year}, {d.strftime('%I:%M:%S %p').lstrip('0')}"


def main() -> None:
    src, out_md, out_stats = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    info, messages = data["info"], data["messages"]

    lines = [f"# {info['title']}", "",
             f"**Session ID:** {info['id']}",
             f"**Created:** {stamp(info['time']['created'])}",
             f"**Updated:** {stamp(info['time']['updated'])}", "",
             f"> Readable copy of `{src.name}` (the `opencode export` output, which is the complete log).",
             "> Same layout as OpenCode's own /export. Only embedded base64 picture data is cut.", "",
             "---", ""]
    prompts, current = [], None
    for msg in messages:
        role = msg["info"]["role"]
        if role == "user":
            text = "\n\n".join(p.get("text", "") for p in msg["parts"] if p["type"] == "text")
            lines += ["## User", "", text.strip(), "", "---", ""]
            current = {"prompt": len(prompts) + 1, "first_line": text.strip().splitlines()[0][:110],
                       "chars": len(text.strip()), "model_calls": 0, "tool_calls": 0, "tool_errors": 0,
                       "input": 0, "cache_read": 0, "output": 0, "reasoning": 0, "cost": 0.0,
                       "context_at_end": 0, "started": msg["info"]["time"]["created"], "ended": 0}
            prompts.append(current)
            continue
        block = ["## Assistant", ""]
        for part in msg["parts"]:
            if part["type"] == "text" and part.get("text", "").strip():
                block += [part["text"].strip(), ""]
            elif part["type"] == "tool":
                state = part.get("state", {})
                block += [f"**Tool: {part.get('tool')}**", "", "**Input:**", "```json",
                          cut(json.dumps(state.get("input", {}), indent=2, ensure_ascii=False)), "```", ""]
                if state.get("status") == "error":
                    block += [f"**Error:** {cut(str(state.get('error', '')))}", ""]
                    if current:
                        current["tool_errors"] += 1
                else:
                    block += [cut(str(state.get("output", ""))).rstrip(), ""]
                if current:
                    current["tool_calls"] += 1
        if len(block) > 2:
            lines += block + ["---", ""]
        if current:
            tok = msg["info"].get("tokens") or {}
            cache = tok.get("cache") or {}
            current["model_calls"] += 1
            current["input"] += tok.get("input", 0)
            current["cache_read"] += cache.get("read", 0)
            current["output"] += tok.get("output", 0)
            current["reasoning"] += tok.get("reasoning", 0)
            current["cost"] += msg["info"].get("cost", 0) or 0
            current["context_at_end"] = tok.get("input", 0) + cache.get("read", 0)
            current["ended"] = (msg["info"].get("time") or {}).get("completed") or current["ended"]

    out_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    for p in prompts:
        p["seconds"] = round((p["ended"] - p["started"]) / 1000) if p["ended"] else None
        p["cost"] = round(p["cost"], 5)
    total = {k: sum(p[k] for p in prompts) for k in
             ("model_calls", "tool_calls", "tool_errors", "input", "cache_read", "output", "reasoning")}
    total["cost"] = round(sum(p["cost"] for p in prompts), 5)
    total["prompts"] = len(prompts)
    total["minutes"] = round((info["time"]["updated"] - info["time"]["created"]) / 60000, 1)
    calls = [m["info"] for m in messages if m["info"]["role"] == "assistant"]
    first, last = calls[0]["tokens"], calls[-1]["tokens"]
    total["context_first_call"] = first["input"] + first["cache"]["read"]
    total["context_last_call"] = last["input"] + last["cache"]["read"]
    total["opencode_session_cost"] = info.get("cost")
    out_stats.write_text(json.dumps({"session": info["id"], "title": info["title"], "model": info.get("model"),
                                     "total": total, "per_prompt": prompts}, indent=1), encoding="utf-8")
    print(f"{out_md.name}: {out_md.stat().st_size / 1024:.0f} KB, {len(lines)} lines")
    print(json.dumps(total))
    for p in prompts:
        print(f"prompt {p['prompt']}: {p['model_calls']} model calls, {p['tool_calls']} tool calls ({p['tool_errors']} failed), "
              f"new in {p['input']}, cached {p['cache_read']}, out {p['output']}, reasoning {p['reasoning']}, "
              f"${p['cost']}, context at end {p['context_at_end']}, {p['seconds']} s | {p['first_line']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
