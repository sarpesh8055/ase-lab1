# Task 2 – specification (original README from lab1.zip, kept for reference)

There is no starter code for this task, only this specification and some helpers.
Read the task description on the lab sheet first.

## Specification

### Allowed dependencies
Python standard library, `numpy`, `rank-bm25`, `tiktoken`, the provided `common/` helpers,
optionally `sentence-transformers` for local embeddings.
Not allowed: LangChain, LlamaIndex, Haystack, agent SDKs, vector databases.

### RAG component – `rag.py`
- Loads all documents from `style_guide/` and splits them into chunks.
- Embeds the chunks, keeps the vectors in memory (a numpy matrix is enough).
- Provides `search(query: str, k: int) -> list[Chunk]`, returning the most similar chunks by cosine similarity.
  Each chunk carries its text and the id of its source document (e.g. `SG-13`).
- Context budget rules:
  - one `search_style_guide` observation may contain at most **1,000 tokens** of style guide text
    (measure with `count_tokens` from `common/llm_client.py`)
  - your system prompt and task description must not contain style guide text

### Agent loop – `agent.py`
The model answers with exactly one JSON object per step:

```json
{"thought": "short reasoning", "action": "<action name>", "args": {}}
```

| Action | Args | What your code does | Observation returned to the model |
|---|---|---|---|
| `search_style_guide` | `{"query": str}` | calls `rag.search` | retrieved chunks with document ids (≤ 1,000 tokens) |
| `read_profiles` | `{}` | reads all `content/*.md` files (not `_template.md`) | profile texts + list of available image files |
| `write_site` | `{}` + the HTML in a ` ```html ` code block directly after the JSON (or `{"html": str}`) | resolves `{{image:...}}` placeholders, saves the file, runs `check_site(..., mode="full")` | the checker report (or an error, e.g. unknown image) |
| `finish` | `{"summary": str}` | accepted only if the last checker report passed | if rejected: the failing checks |

Behaviour your loop must have:
- A maximum number of steps (e.g. 25). Stop with a clear message when it is reached.
- If the model output is not valid JSON or uses an unknown action or wrong args: don't crash.
  Send an error observation back and continue. Count it as a step.
- The model must never write base64 image data. It uses placeholders like `<img src="{{image:anna.jpg}}" alt="...">`.
- Human in the loop: after an accepted `finish`, ask the user for feedback on the terminal.
  Non-empty feedback is appended as a new user message and the loop continues. Empty input ends the run.
- Don't use the native function-calling / `tools` API. You build the protocol yourselves.
- Set `max_tokens` high enough (or don't set it), otherwise the answer is cut off.
- Embeddings: use the gateway embedding model via `llm.embed(...)` (free), or a local model.

### Command line
```bash
uv run python task2_own_agent/agent.py --content task1_opencode/content --out task2_own_agent/site/index.html
```

### Logs
- Store every message sent to and received from the model, with step numbers, in `task2_own_agent/logs/run_XX.jsonl`.
- Submit the logs of at least one complete run that produced your submitted `site/index.html`.

### What your README must contain
- how to run the agent
- your design decisions: chunking, embedding model, k, prompt design, how you handle invalid output
- known limitations
