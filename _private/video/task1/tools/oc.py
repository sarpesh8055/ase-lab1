"""Drive an OpenCode terminal UI through the local control port it opens with --port.

Stdlib only. Every action is appended to a timeline file so it can be matched
against a screen recording later.

    python oc.py --port P --state DIR health
    python oc.py --port P --state DIR prompt <text-file>      type the text into the UI and submit it
    python oc.py --port P --state DIR watch [--auto] [--timeout S] [--delay S]
    python oc.py --port P --state DIR reply <request-id> once|always|reject [--message TEXT] [--delay S]
    python oc.py --port P --state DIR tui <command>           e.g. session.page.up
    python oc.py --port P --state DIR tail [--all]            what the agent said/did since last time
    python oc.py --port P --state DIR stats                   prompts, tokens and cost of the session

`watch` follows the session until it is idle. Permission requests are printed.
With --auto, requests that match the policy below are approved after a short,
visible delay; everything else stops the watch (exit code 3) for a human decision.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---- approval policy (only used with --auto) --------------------------------
TASK_DIR = Path(__file__).resolve().parents[4] / "task1_opencode"  # <repo>/_private/video/task1/tools/oc.py
REPO_DIR = TASK_DIR.parent
# The agent may create/change files anywhere in the task folder, except the
# team's own content, the logs/screenshots and the course's scripts ...
PROTECTED = [TASK_DIR / "content", TASK_DIR / "conversation", TASK_DIR / "screenshots",
             TASK_DIR / "check_site.py", TASK_DIR / "embed_images.py", TASK_DIR / "opencode.json",
             TASK_DIR / "README.md"]
# ... and may only run these commands by itself.
_PY = r"(?:uv run )?(?:python|python3|py)(?:\.exe)?"
_ARG = r"""(?:\s+(?:--?[\w-]+|"[\w ./\\:-]+"|'[\w ./\\:-]+'|[\w./\\:-]+))*"""
BASH_ALLOW = [
    rf"{_PY}\s+\.?[/\\]?check_site\.py{_ARG}",
    rf"{_PY}\s+\.?[/\\]?embed_images\.py{_ARG}",
    r"git diff --check",      # read-only git look-ups the agent likes to finish with
    r"git diff --stat",
    r"git status --short",
]
# Reading (not writing) these folders outside the task folder is fine.
EXTERNAL_READ_OK = [REPO_DIR / "common"]


def norm(p: str, base: Path = REPO_DIR) -> Path:
    """Absolute path for something OpenCode reports (relative paths are relative to the git root)."""
    return Path(os.path.normpath(os.path.join(str(base), p.replace("/", os.sep))))


def edit_allowed(path: Path) -> bool:
    return inside(path, TASK_DIR) and not any(inside(path, p) for p in PROTECTED)


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


_CALC_FORBIDDEN = re.compile(
    r"\b(import(?!\s+math\b)|open|os|sys|subprocess|eval|exec|compile|input|socket|urllib|requests|pathlib|Path|"
    r"shutil|globals|locals|vars|getattr|setattr|delattr|write|read|remove|unlink|system|popen|breakpoint)\b")


def is_pure_colour_maths(command: str) -> bool:
    """True for the throwaway `python -c "..."` contrast-ratio sums the agent likes to run:
    only arithmetic on hex colours and print(), nothing that can reach files, the network or other programs."""
    m = re.fullmatch(r'python -c "(.*)"', command, re.S)
    if not m:
        return False
    code = m.group(1)
    return ("lambda" in code and re.search(r"#[0-9a-fA-F]{6}\b", code) is not None and "print(" in code
            and "__" not in code and '"' not in code and "`" not in code and "$" not in code
            and not _CALC_FORBIDDEN.search(code))


def decide(req: dict):
    """Return ("once", reason) to approve, or None to leave it to a human."""
    perm = req.get("permission", "")
    meta = req.get("metadata") or {}
    patterns = req.get("patterns") or []
    if perm == "bash":
        command = (meta.get("command") or " ".join(patterns)).strip()
        if is_pure_colour_maths(command):
            return "once", "one-line colour-contrast calculation, touches no files"
        if ".." in command or ":" in command:  # nothing outside the task folder without a human look
            return None
        if any(re.fullmatch(rx, command) for rx in BASH_ALLOW):
            return "once", "command is on the allow list"
        return None
    if perm == "edit":
        files = [Path(f["filePath"]) for f in meta.get("files") or [] if f.get("filePath")]
        if not files:
            raw = meta.get("filepath") or (patterns[0] if patterns else "")
            files = [norm(raw)] if raw else []
        if files and all(edit_allowed(f) for f in files):
            return "once", "only touches agent-owned files in the task folder"
        return None
    if perm == "external_directory":
        targets = [norm(p.rstrip("*").rstrip("/\\")) for p in patterns] or [Path("?")]
        if all(any(inside(t, ok) for ok in EXTERNAL_READ_OK) for t in targets):
            return "once", "folder is on the read list"
        return None
    return None


# ---- plumbing ----------------------------------------------------------------
class Api:
    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}"

    def call(self, method: str, path: str, body=None, timeout: float = 30):
        data, headers = None, {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None


class State:
    def __init__(self, folder: str):
        self.dir = Path(folder)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "state.json"
        self.data = json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else {}

    def save(self) -> None:
        self.file.write_text(json.dumps(self.data, indent=1), encoding="utf-8")

    def log(self, event: str, **detail) -> None:
        row = {"t": round(time.time(), 2), "clock": time.strftime("%H:%M:%S"), "event": event, **detail}
        with open(self.dir / "timeline.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def short(text, n: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def describe(req: dict) -> str:
    meta = req.get("metadata") or {}
    bits = [f"permission={req.get('permission')}", f"patterns={req.get('patterns')}"]
    for key in ("command", "filepath", "filePath", "path", "description", "parentDir"):
        if key in meta:
            bits.append(f"{key}={short(meta[key], 400)}")
    if "diff" in meta:
        diff = str(meta["diff"])
        plus = sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        minus = sum(1 for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---"))
        bits.append(f"diff=+{plus}/-{minus} lines")
    return "  ".join(bits)


def current_session(api: Api, state: State):
    if state.data.get("session"):
        return state.data["session"]
    status = api.call("GET", "/session/status") or {}
    busy = [sid for sid, st in status.items() if st.get("type") in ("busy", "retry")]
    if busy:
        state.data["session"] = busy[0]
        state.save()
        return busy[0]
    return None


def print_tail(api: Api, state: State, everything: bool = False) -> None:
    sid = current_session(api, state)
    if not sid:
        print("(no session yet)")
        return
    messages = api.call("GET", f"/session/{sid}/message") or []
    seen = 0 if everything else state.data.get("parts_seen", 0)
    count = 0
    for msg in messages:
        role = msg["info"].get("role")
        for part in msg.get("parts", []):
            count += 1
            if count <= seen:
                continue
            kind = part.get("type")
            if kind == "text":
                print(f"[{role}] {short(part.get('text', ''), 1500)}")
            elif kind == "tool":
                st = part.get("state", {})
                inp = st.get("input") or {}
                brief = {k: short(v, 160) for k, v in inp.items() if k not in ("content", "newString", "oldString", "patchText")}
                extra = ""
                if st.get("status") == "error":
                    extra = "  ERROR: " + short(st.get("error", ""), 500)
                elif part.get("tool") == "bash":
                    extra = "  -> " + short(st.get("output", ""), 700)
                print(f"   tool {part.get('tool')} [{st.get('status')}] {json.dumps(brief, ensure_ascii=False)}{extra}")
            elif kind in ("step-finish",):
                tok = part.get("tokens") or {}
                print(f"   step done: in={tok.get('input')} out={tok.get('output')} reasoning={tok.get('reasoning')} "
                      f"cache_read={(tok.get('cache') or {}).get('read')} cost=${part.get('cost')}")
    state.data["parts_seen"] = count
    state.save()


def cmd_watch(api: Api, state: State, a) -> int:
    t0 = time.time()
    seen_busy, idle_polls, told_retry = False, 0, False
    while True:
        try:
            questions = api.call("GET", "/question") or []
        except urllib.error.HTTPError:
            questions = []
        if questions:
            print("QUESTION FROM THE AGENT (needs an answer):")
            print(json.dumps(questions, indent=1, ensure_ascii=False)[:4000])
            state.log("question", count=len(questions))
            return 5
        for req in api.call("GET", "/permission") or []:
            verdict = decide(req) if a.auto else None
            if verdict is None:
                print("NEEDS DECISION:", describe(req))
                print(json.dumps({k: (short(v, 1500) if k == "metadata" else v) for k, v in req.items()},
                                 indent=1, ensure_ascii=False)[:5000])
                state.log("permission.asked", id=req["id"], what=describe(req), auto=False)
                return 3
            reply, reason = verdict
            state.log("permission.asked", id=req["id"], what=describe(req), auto=True)
            print(f"asked: {describe(req)}\n   -> approving {reply} in {a.delay:.0f} s ({reason})", flush=True)
            time.sleep(a.delay)
            api.call("POST", f"/permission/{req['id']}/reply", {"reply": reply})
            state.log("permission.replied", id=req["id"], reply=reply, reason=reason)
        sid = current_session(api, state)
        status = (api.call("GET", "/session/status") or {})
        kind = status.get(sid, {}).get("type", "idle") if sid else "idle"
        if kind in ("busy", "retry"):
            seen_busy, idle_polls = True, 0
            if kind == "retry" and not told_retry:
                print("RETRYING:", short(status[sid].get("message", ""), 300), flush=True)
                state.log("retry", message=short(status[sid].get("message", ""), 300))
                told_retry = True
        else:
            idle_polls += 1
            if (seen_busy and idle_polls >= 4) or (not seen_busy and time.time() - t0 > a.grace):
                print("IDLE" if seen_busy else "IDLE (never saw it busy)")
                state.log("idle", seen_busy=seen_busy)
                return 0
        if time.time() - t0 > a.timeout:
            print(f"STILL BUSY after {a.timeout:.0f} s")
            return 4
        time.sleep(0.7)


def cmd_stats(api: Api, state: State) -> None:
    sid = current_session(api, state)
    messages = api.call("GET", f"/session/{sid}/message") or []
    prompts = sum(1 for m in messages if m["info"].get("role") == "user")
    total = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cost": 0.0}
    rows = []
    for m in messages:
        info = m["info"]
        if info.get("role") != "assistant":
            continue
        tok = info.get("tokens") or {}
        cache = tok.get("cache") or {}
        row = {"input": tok.get("input", 0), "output": tok.get("output", 0), "reasoning": tok.get("reasoning", 0),
               "cache_read": cache.get("read", 0), "cost": info.get("cost", 0) or 0}
        rows.append(row)
        for key in total:
            total[key] += row[key]
    print(json.dumps({"session": sid, "prompts": prompts, "assistant_messages": len(rows), "total": total,
                      "per_message": rows}, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--state", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    p = sub.add_parser("prompt")
    p.add_argument("file")
    p.add_argument("--pause", type=float, default=2.5, help="seconds the text stays in the input box before sending")
    w = sub.add_parser("watch")
    w.add_argument("--auto", action="store_true")
    w.add_argument("--timeout", type=float, default=540)
    w.add_argument("--delay", type=float, default=3)
    w.add_argument("--grace", type=float, default=25)
    r = sub.add_parser("reply")
    r.add_argument("id")
    r.add_argument("reply", choices=["once", "always", "reject"])
    r.add_argument("--message")
    r.add_argument("--delay", type=float, default=0)
    t = sub.add_parser("tui")
    t.add_argument("command")
    tl = sub.add_parser("tail")
    tl.add_argument("--all", action="store_true")
    sub.add_parser("stats")
    sub.add_parser("perms")
    n = sub.add_parser("note")
    n.add_argument("text")
    a = ap.parse_args()

    api, state = Api(a.port), State(a.state)
    if a.cmd == "health":
        print(api.call("GET", "/global/health"))
    elif a.cmd == "prompt":
        text = Path(a.file).read_text(encoding="utf-8").strip()
        api.call("POST", "/tui/append-prompt", {"text": text})
        state.log("prompt.typed", chars=len(text), first_line=short(text.splitlines()[0], 120))
        time.sleep(a.pause)
        api.call("POST", "/tui/submit-prompt")
        state.log("prompt.sent")
        state.data["prompts"] = state.data.get("prompts", 0) + 1
        state.save()
        print(f"sent prompt ({len(text)} characters)")
    elif a.cmd == "watch":
        code = cmd_watch(api, state, a)
        print("---- since last look ----")
        print_tail(api, state)
        return code
    elif a.cmd == "reply":
        time.sleep(a.delay)
        body = {"reply": a.reply}
        if a.message:
            body["message"] = a.message
        print(api.call("POST", f"/permission/{a.id}/reply", body))
        state.log("permission.replied", id=a.id, reply=a.reply, message=a.message, auto=False)
    elif a.cmd == "tui":
        print(api.call("POST", "/tui/execute-command", {"command": a.command}))
        state.log("tui.command", command=a.command)
    elif a.cmd == "tail":
        print_tail(api, state, everything=a.all)
    elif a.cmd == "stats":
        cmd_stats(api, state)
    elif a.cmd == "perms":
        print(json.dumps(api.call("GET", "/permission"), indent=1, ensure_ascii=False)[:6000])
    elif a.cmd == "note":
        state.log("note", text=a.text)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
