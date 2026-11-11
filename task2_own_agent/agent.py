"""Task 2 – our own small coding agent that builds the team website.

The model answers with exactly one JSON object per step (our own protocol, no native tool calling):

    {"thought": "short reasoning", "action": "<action name>", "args": {...}}

For write_site the HTML follows the JSON in a ```html code block (or is given as args.html).

Run from the repository root:
    uv run python task2_own_agent/agent.py --content task1_opencode/content --out task2_own_agent/site/index.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from common.embed_images import PLACEHOLDER, embed_images  # noqa: E402
from common.llm_client import LLMClient, count_tokens  # noqa: E402
from common.site_checker import check_site, member_names_from_content  # noqa: E402
from rag import StyleGuideIndex, format_observation, style_guide_tokens  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}

# ----------------------------------------------------------------------------- prompts
# NOTE: the system prompt and task contain NO style guide text. The agent must retrieve the rules.

SYSTEM_PROMPT = """You are a web development agent. You build a single-file team website (HTML + CSS + JavaScript)
by calling actions. You work step by step. In EVERY reply you output exactly ONE JSON object and nothing else
(except for write_site, see below):

{"thought": "<one or two sentences>", "action": "<action name>", "args": {...}}

Available actions:

1. search_style_guide  args: {"query": "<what you want to know>"}
   Searches the team's web style guide (a private document set you have never seen). Returns the most
   relevant rules with their document ids. Ask one specific topic per query.

2. read_profiles  args: {}
   Returns the profiles of all team members and the list of available image files.

3. write_site  args: {}
   Saves the complete website and runs an automatic checker. Put the COMPLETE HTML document in a
   ```html code block directly after the JSON object. Example reply:
   {"thought": "Writing the first version.", "action": "write_site", "args": {}}
   ```html
   <!DOCTYPE html>
   ...
   ```
   The observation is the checker report. Every write replaces the whole file, so always send the full page.

4. finish  args: {"summary": "<what you built>"}
   Ends the task. Only accepted after the last write_site passed ALL checks.

Rules:
- Never write base64 or data: URIs for images. Use placeholders: <img src="{{image:<file name>}}" alt="...">,
  with a file name from the list returned by read_profiles. The program embeds the images.
- The page must be self-contained: no external CSS, JS, fonts or images (no CDNs, no Google Fonts).
- The style guide is binding. Documents can be DEPRECATED: then follow the ACTIVE document that replaces it.
  Look rules up before you write; do not guess colors, ids, class names, footer text or similar details.
- Do not repeat a search you already made. Use the results you have.
- Reply with JSON only. No markdown around the JSON, no text before it."""

TASK_PROMPT = """Task: build our team website as one standalone HTML file.

Requirements:
- Introduce the team and EVERY team member with a card (photo, study background, interests, fun fact,
  opinion on AI in software engineering today, view on the next 5-10 years, hot take).
- Responsive (phone and desktop) and a day/night mode toggle.
- A section with the team's shared view on AI and the future of software engineering
  (summarise the members' opinions into one common view).
- Funny and creative, but readable.
- Follow our web style guide in every detail (structure, metadata, colors, theming, components,
  typography, responsive behaviour, footer, motion, ...).

Suggested plan: read the profiles, research the style guide topic by topic, write the site,
fix whatever the checker reports, then finish."""

ACTION_ARGS = {
    "search_style_guide": {"query": str},
    "read_profiles": {},
    "write_site": {},  # optional "html": str
    "finish": {"summary": str},
}

# ----------------------------------------------------------------------------- parsing


class ProtocolError(Exception):
    """Model output that does not follow the protocol. The message is sent back to the model."""


def extract_json_object(text: str) -> tuple[dict, int]:
    """Find the first JSON object in `text`. Returns (object, end index).

    Tolerates a ```json fence or some text before the object, because models do that
    occasionally; everything else is a protocol error.
    """
    decoder = json.JSONDecoder()
    last_error = None
    for match in re.finditer(r"\{", text):
        try:
            obj, end = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(obj, dict):
            return obj, end
    if last_error:
        raise ProtocolError(f"Your reply is not valid JSON ({last_error.msg} at position {last_error.pos}).")
    raise ProtocolError("Your reply contains no JSON object.")


def parse_reply(text: str) -> tuple[str, dict, str | None]:
    """Returns (action, args, html or None). Raises ProtocolError with a helpful message."""
    if not text.strip():
        raise ProtocolError("Your reply was empty.")
    obj, end = extract_json_object(text)
    action = obj.get("action")
    args = obj.get("args", {})
    if not isinstance(action, str):
        raise ProtocolError('The JSON object needs a string field "action".')
    if action not in ACTION_ARGS:
        raise ProtocolError(f"Unknown action '{action}'. Valid actions: {', '.join(ACTION_ARGS)}.")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ProtocolError('"args" must be a JSON object.')

    html = None
    if action == "write_site":
        if isinstance(args.get("html"), str):
            html = args.pop("html")
        else:
            block = re.search(r"```html\s*\n(.*?)(?:\n```|\Z)", text[end:], re.S | re.I)
            if block:
                html = block.group(1)
        if not html or "<html" not in html.lower():
            raise ProtocolError(
                "write_site needs the complete HTML document in a ```html code block directly after the JSON object."
            )
        if block_was_cut(text[end:]) and "</html>" not in html.lower():
            raise ProtocolError("The HTML code block is incomplete (no closing ``` and no </html>). Send the full page.")

    expected = ACTION_ARGS[action]
    for name, typ in expected.items():
        if name not in args:
            raise ProtocolError(f"Action '{action}' needs the argument '{name}'.")
        if not isinstance(args[name], typ) or (typ is str and not args[name].strip()):
            raise ProtocolError(f"Argument '{name}' of '{action}' must be a non-empty {typ.__name__}.")
    unknown = set(args) - set(expected)
    if unknown:
        raise ProtocolError(f"Action '{action}' got unknown arguments: {sorted(unknown)}. Expected: {list(expected) or 'none'}.")
    return action, args, html


def block_was_cut(rest: str) -> bool:
    return "```html" in rest.lower() and rest.lower().split("```html", 1)[1].count("```") == 0


# ----------------------------------------------------------------------------- the agent


class SiteAgent:
    def __init__(self, llm: LLMClient, index: StyleGuideIndex, content_dir: Path, out_path: Path,
                 k: int = 5, max_steps: int = 25, max_tokens: int | None = None, interactive: bool = True):
        self.llm = llm
        self.index = index
        self.content_dir = content_dir
        self.images_dir = content_dir / "images"
        self.out_path = out_path
        self.k = k
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.interactive = interactive

        self.member_names = member_names_from_content(content_dir)
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TASK_PROMPT},
        ]
        self.step = 0
        self.last_report = None          # CheckReport of the last write_site
        self.searches: dict[str, str] = {}
        self.recent_actions: list[str] = []

    # -------------------------------------------------------------- logging helpers

    def log(self, kind: str, **data) -> None:
        self.llm.log_event({"event": kind, "step": self.step, **data})

    def say(self, text: str) -> None:
        print(text, flush=True)

    # -------------------------------------------------------------- main loop

    def run(self) -> bool:
        self.log("start", content_dir=str(self.content_dir), out=str(self.out_path),
                 members=self.member_names, k=self.k, max_steps=self.max_steps, model=self.llm.model)
        self.say(f"Members found: {', '.join(self.member_names) or 'none'}")
        round_no = 1
        while True:
            finished = self.run_round()
            if not finished:
                self.say(f"\nStopped: step limit of {self.max_steps} steps reached without an accepted finish.")
                self.log("step_limit_reached", round=round_no)
                return False
            feedback = self.ask_feedback()
            if not feedback:
                self.log("end", reason="no feedback", usage=self.llm.usage_summary())
                self.say(f"\nDone. {self.llm.usage_summary()}")
                return True
            round_no += 1
            self.log("human_feedback", round=round_no, feedback=feedback)
            self.last_report = None  # the page has to be checked again after changes
            self.messages.append({"role": "user", "content":
                                  f"Feedback from the team on your website:\n{feedback}\n\n"
                                  "Change the website accordingly (write_site with the full page), "
                                  "make sure all checks still pass, then finish."})

    def run_round(self) -> bool:
        """Runs steps until an accepted finish (True) or the step limit (False)."""
        steps_in_round = 0
        while steps_in_round < self.max_steps:
            steps_in_round += 1
            self.step += 1
            reply = self.call_model()
            self.messages.append({"role": "assistant", "content": reply})
            try:
                action, args, html = parse_reply(reply)
            except ProtocolError as exc:
                self.say(f"[{self.step:2}] invalid output: {exc}")
                self.log("protocol_error", error=str(exc), reply_head=reply[:300])
                self.observe(f"ERROR: {exc}\nReply again with exactly one JSON object in the required format.")
                continue

            thought = reply_thought(reply)
            self.say(f"[{self.step:2}] {action} {json.dumps(args, ensure_ascii=False)[:100]}  | {thought[:100]}")
            self.log("action", action=action, args=args, thought=thought, html_chars=len(html or ""))

            if action == "finish":
                if self.last_report is not None and self.last_report.passed:
                    self.log("finish_accepted", summary=args["summary"])
                    self.say(f"     finish accepted: {args['summary']}")
                    self.observe("finish accepted.")
                    return True
                reason = ("You have not written the site yet (or not since the last feedback)."
                          if self.last_report is None else
                          "The last checker report has failures:\n" + self.last_report.summary(only_failures=True))
                self.log("finish_rejected", reason=reason)
                self.say("     finish rejected")
                self.observe(f"finish REJECTED. {reason}\nFix the problems with write_site first.")
                continue

            observation = self.execute(action, args, html)
            observation = self.repetition_hint(action, args) + observation
            self.observe(observation)
        return False

    def call_model(self) -> str:
        self.compact_history()
        self.log("model_call", n_messages=len(self.messages),
                 context_tokens_estimate=sum(count_tokens(m["content"]) for m in self.messages))
        try:
            return self.llm.chat(self.messages, max_tokens=self.max_tokens)
        except Exception as exc:  # network/budget errors after the client's own retries
            self.log("model_error", error=repr(exc))
            raise

    def observe(self, text: str) -> None:
        self.messages.append({"role": "user", "content": f"OBSERVATION (step {self.step}):\n{text}"})
        self.log("observation", text=text)

    # -------------------------------------------------------------- actions

    def execute(self, action: str, args: dict, html: str | None) -> str:
        if action == "search_style_guide":
            return self.do_search(args["query"].strip())
        if action == "read_profiles":
            return self.do_read_profiles()
        if action == "write_site":
            return self.do_write_site(html or "")
        raise AssertionError(action)

    def do_search(self, query: str) -> str:
        key = query.lower()
        if key in self.searches:
            return (f'You already searched for "{query}". Use the earlier result (step {self.searches[key]}) '
                    "or search for a different topic.")
        chunks = self.index.search(query, self.k)
        text, ids = format_observation(query, chunks)
        self.searches[key] = str(self.step)
        self.log("retrieval", query=query, doc_ids=ids,
                 scores=[round(c.score, 4) for c in chunks], style_guide_tokens=style_guide_tokens(text))
        return text

    def do_read_profiles(self) -> str:
        profiles = sorted(p for p in self.content_dir.glob("*.md") if not p.name.startswith("_"))
        images = sorted(p.name for p in self.images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS) \
            if self.images_dir.is_dir() else []
        parts = [f"{len(profiles)} team members: {', '.join(self.member_names)}",
                 f"Available image files (use as {{{{image:<file>}}}}): {', '.join(images) or 'none'}"]
        for p in profiles:
            parts.append(f"===== {p.name} =====\n{strip_comments(p.read_text(encoding='utf-8')).strip()}")
        return "\n\n".join(parts)

    def do_write_site(self, html: str) -> str:
        if re.search(r"data:image/[^;]+;base64,", html):
            return ("ERROR: the HTML contains base64 image data. Never write image data yourself; "
                    "use <img src=\"{{image:<file>}}\"> placeholders. Nothing was saved.")
        n_placeholders = len(PLACEHOLDER.findall(html))
        try:
            final = embed_images(html, self.images_dir)
        except (FileNotFoundError, ValueError) as exc:
            return f"ERROR while embedding images: {exc}\nNothing was saved."
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text(final, encoding="utf-8")
        report = check_site(final, mode="full", member_names=self.member_names,
                            file_size=self.out_path.stat().st_size)
        self.last_report = report
        n_pass = sum(r.passed for r in report.results)
        self.say(f"     saved {self.out_path} ({self.out_path.stat().st_size / 1024:.0f} KB, "
                 f"{n_placeholders} images) -> checker {n_pass}/{len(report.results)}")
        self.log("checker", report=report.to_dict(), html_chars=len(html), placeholders=n_placeholders)
        return (f"Saved ({n_placeholders} image placeholders embedded). Checker report:\n{report.summary()}"
                + ("\nAll checks passed. You may call finish." if report.passed else
                   "\nFix the failing checks (search the style guide for the relevant rules if needed)."))

    # -------------------------------------------------------------- robustness

    def repetition_hint(self, action: str, args: dict) -> str:
        sig = action + json.dumps(args, sort_keys=True)
        self.recent_actions.append(sig)
        if len(self.recent_actions) >= 3 and len(set(self.recent_actions[-3:])) == 1:
            self.log("repetition_detected", action=action)
            return ("NOTE: you made the same action three times in a row. That will not change the result. "
                    "Do something different.\n\n")
        return ""

    def compact_history(self) -> None:
        """Keep the context small: only the newest write_site keeps its full HTML.

        Older full-page HTML blocks are replaced by a short note. The model always has its latest
        page to edit, but the context doesn't grow by a whole website per write.
        """
        writes = [i for i, m in enumerate(self.messages) if m["role"] == "assistant" and "```html" in m["content"]]
        for i in writes[:-1]:
            content = self.messages[i]["content"]
            head = content.split("```html", 1)[0]
            self.messages[i]["content"] = head + "```html\n[older version of the page removed to save context; " \
                                                 "the newest version is further below]\n```"

    def ask_feedback(self) -> str:
        if not self.interactive:
            return ""
        print("\nThe agent finished. Open the site and give feedback (empty line = done):")
        try:
            return input("feedback> ").strip()
        except EOFError:
            return ""


def reply_thought(reply: str) -> str:
    try:
        obj, _ = extract_json_object(reply)
        return str(obj.get("thought", ""))
    except ProtocolError:
        return ""


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def next_log_path(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for p in logs_dir.glob("run_*.jsonl") if (m := re.match(r"run_(\d+)", p.stem))]
    return logs_dir / f"run_{(max(numbers, default=0) + 1):02d}.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Our own coding agent for the team website (Task 2).")
    parser.add_argument("--content", type=Path, default=REPO / "task1_opencode" / "content",
                        help="directory with <firstname>.md profiles and images/")
    parser.add_argument("--out", type=Path, default=HERE / "site" / "index.html", help="output HTML file")
    parser.add_argument("--model", default=None, help="chat model (default: $LAB_CHAT_MODEL)")
    parser.add_argument("--max-steps", type=int, default=25, help="step limit per round (default 25)")
    parser.add_argument("-k", type=int, default=5, help="chunks retrieved per search (default 5)")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="max output tokens per model call (default: not set)")
    parser.add_argument("--no-feedback", action="store_true", help="don't ask for human feedback at the end")
    parser.add_argument("--log", type=Path, default=None, help="log file (default: logs/run_XX.jsonl)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    log_path = args.log or next_log_path(HERE / "logs")
    llm = LLMClient(model=args.model, log_path=log_path)
    print(f"Log: {log_path}\nModel: {llm.model}")
    index = StyleGuideIndex.build(llm)
    print(f"Style guide index: {len(index.chunks)} chunks")

    agent = SiteAgent(llm, index, args.content, args.out, k=args.k, max_steps=args.max_steps,
                      max_tokens=args.max_tokens, interactive=not args.no_feedback)
    ok = agent.run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
