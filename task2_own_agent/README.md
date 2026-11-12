# Task 2 – Our own (small) coding agent

A Python agent that builds the team website on its own. It reads the profiles, retrieves the
rules of the "UPB Agentic SE Web Style Guide" with RAG, writes the page, runs the checker and fixes
what fails. No frameworks: only the standard library, `numpy`, `tiktoken` and the provided `common/` helpers.

## How to run

From the repository root (university network or VPN, `.env` with your gateway key):

```bash
uv run python task2_own_agent/agent.py --content task1_opencode/content --out task2_own_agent/site/index.html
```

When the agent has finished (all checks passed), it asks for feedback on the terminal.
Type feedback and press Enter to let it continue; an empty line ends the run.

| Option | Default | Meaning |
|---|---|---|
| `--content DIR` | `task1_opencode/content` | profiles (`<firstname>.md`) and `images/` |
| `--out FILE` | `task2_own_agent/site/index.html` | where the site is written |
| `--model ID` | `$LAB_CHAT_MODEL` (`openai.gpt-6-luna`) | chat model, e.g. `kiconnect.qwen3.8-27b` as free fallback |
| `--max-steps N` | 25 | step limit per round (initial task, and each feedback round) |
| `-k N` | 5 | chunks retrieved per search |
| `--max-tokens N` | not set | output token limit per call (keep it unset: reasoning tokens count too) |
| `--no-feedback` | off | skip the human feedback prompt (non-interactive runs) |
| `--log FILE` | `task2_own_agent/logs/run_XX.jsonl` | log file (XX is numbered automatically) |

Retrieval on its own:

```bash
uv run python task2_own_agent/rag.py "night mode colors"   # top chunks, as the agent sees them
uv run python task2_own_agent/rag.py --eval                # sanity check: 18 queries -> expected active document
```

## Files

| File | Content |
|---|---|
| `rag.py` | chunking, embedding, `StyleGuideIndex.search(query, k)`, observation formatting (≤ 1,000 tokens), retrieval sanity check |
| `agent.py` | JSON action protocol, parser, agent loop, actions, human feedback, logging |
| `logs/run_XX.jsonl` | every request/response of a run, plus our events (steps, actions, retrievals, checker reports, feedback) |
| `site/index.html` | the generated website |

## Architecture

```
            ┌─────────────────────────── agent loop (max 25 steps per round) ───────────────────────────┐
 task  ──►  │ messages ──► LLM ──► reply ──► parse_reply ──► action ──► execute ──► OBSERVATION message │
            │                                   │ invalid?            │                                │
            │                                   └─► ERROR observation  ├─ search_style_guide ─► rag.search (k chunks, ≤1000 tok)
            │                                                          ├─ read_profiles ─────► content/*.md + image list
            │                                                          ├─ write_site ────────► embed_images ─► save ─► check_site(full)
            │                                                          └─ finish ────────────► accepted only if last check passed
            └─────────────────────────────────────────────────────────────────────────────────────────────┘
                     accepted finish ──► ask human ──► feedback? ──► new user message, next round  |  empty ──► end
```

The model decides which rules to look up, in which order, when it knows enough to write,
and how to fix a failed check. Our code only executes actions and enforces the rules of the protocol.

## Design decisions

### Protocol
One JSON object per reply: `{"thought": ..., "action": ..., "args": {...}}`.
For `write_site` the HTML comes in a ```` ```html ```` block directly after the JSON (`{"html": ...}` in args is also
accepted). That avoids escaping a whole web page inside a JSON string.

### Handling invalid output
`parse_reply` raises a `ProtocolError` with a specific message. The loop sends it back as an
`OBSERVATION: ERROR ...` and continues; it counts as a step. Cases handled:

- empty reply, no JSON, broken JSON (the decoder error and position are given back)
- a ```` ```json ```` fence or text before the object is tolerated (we look for the first valid JSON object)
- unknown action, `args` not an object, missing / empty / wrongly typed / unknown arguments
- `write_site` without an HTML block, or a cut-off block (no closing fence and no `</html>`, e.g. `finish_reason: length`)
- base64 image data written by the model (rejected, nothing saved)
- unknown image file in a `{{image:...}}` placeholder (error lists the available files)
- `finish` before a passing check: rejected, the failing checks are given back
- the same search twice: the agent gets "you already searched this" instead of the same chunks again
- the same action three times in a row: a note that repeating does not change anything
- never calling `finish`: the step limit stops the run with a clear message (logged as `step_limit_reached`)

### Chunking
The style guide is small (55 documents, about 4,000 words, at most ~200 tokens per document).
We split each document at its `##` headings (66 chunks), and split sections longer than
300 tokens further at paragraphs/list items (doesn't happen with the current guide).
Every chunk starts with the document header: `[SG-13] Night mode palette (version 2)`, `Status: ...`, `Category: ...`.
So every chunk on its own says where it comes from and whether it is ACTIVE or DEPRECATED, and the title
is part of the embedding. Fixed-size chunks would cut rules in half and separate a rule from its status line.
No overlap is needed, because the chunks follow the document structure.

### Embeddings and search
`kiconnect.qwen3-embedding-8b` through the gateway (free, 4096 dimensions). Vectors are L2-normalised
and kept in a numpy matrix; search is a dot product (= cosine similarity). They are cached in
`.cache/` by a hash of the model and the chunk texts, so the guide is embedded only once.

### k and the 1,000-token limit
k = 5. Our sanity check (`rag.py --eval`, 18 hand-written queries with the active document that must be found)
gives hit@1 = 14/18, hit@3 = 18/18, **hit@5 = 18/18**. At k = 1 the active version is often lost, because the
deprecated version of a rule is very similar and often ranks first (e.g. "mobile breakpoint width" → SG-49
(deprecated) before SG-50). We use k = 5 rather than 3 as a margin for vaguer queries written by the model
(which often ask about several topics at once); it still fits easily in the 1,000-token budget.
`format_observation` adds chunks in rank order while the style guide text stays ≤ 1,000 tokens
(`count_tokens`); a chunk that doesn't fit is skipped, not cut in half. In practice a search returns 450–650 tokens.
Deprecated chunks are not removed (the model should see that a rule changed), but they get the line
`(!) This document is DEPRECATED. Follow the document that replaces it.`

### Prompt design
- The system prompt explains the protocol, the four actions with an example for `write_site`, and general rules
  (placeholders for images, no external resources, deprecated documents, don't repeat searches, JSON only).
- The task prompt lists the requirements from the lab sheet and a suggested plan.
- Neither contains style guide text: every rule the agent follows comes from a `search_style_guide` observation.
- Observations are user messages starting with `OBSERVATION (step N):`.

### Context growth
Every turn sends the whole history again. Searches add ~600 tokens each; a full page is ~3,000+ tokens.
To stop the context from growing by a full page per write, `compact_history` keeps only the **newest** HTML;
older HTML blocks are replaced by a short note. In run_01 the estimated context grew from 620 tokens (step 1)
to ~9,400 tokens (step 11). With 100 steps the context would be dominated by search results; the
next step would be to summarise or drop old observations.

### Logs
`LLMClient(log_path=logs/run_XX.jsonl)` logs every request (the full message list) and response with tokens
and cost. We add events with `llm.log_event`: `start`, `model_call` (step, number of messages, context size),
`action`, `retrieval` (query, doc ids, scores, tokens), `checker` (full report), `protocol_error`,
`finish_accepted` / `finish_rejected`, `human_feedback`, `step_limit_reached`, `end`.

## Results

| Run | Steps | Searches | Checker | Calls | Tokens (prompt + completion) | Cost |
|---|---|---|---|---|---|---|
| run_01 (no feedback) | 11 | 8 | 25/25 at the first write | 19 | 42,680 + 12,922 | $0.0081 |
| run_02 (1 feedback round) | 14 | 9 | 25/25, still 25/25 after feedback | 23 | 69,560 + 8,656 | $0.0068 |
| run_03 (all five members, 1 feedback round; produced `site/index.html`) | 14 | 9 | 25/25 at the first write, still 25/25 after feedback | 28 | 95,862 + 10,915 | $0.0086 |

(Calls include the embedding calls for the queries.)

## Known limitations

- The checker only tests some rules. Rules it does not test (card order, bio length, tone, badge length, ...)
  are only followed if the agent happened to retrieve them. A page that passes 25/25 can still break some rules.
- The agent decides itself what to search for. If it never asks about a topic, it doesn't know the rule.
  In run_02 the feedback asked for a statistics section, and the agent added it without searching the
  matching document (SG-62).
  In run_03 the first page passed 25/25 although it had no bio (SG-08) and its hot-take badges did not start
  with 🔥 (SG-31): the checker only tests that a badge exists, and the agent had not searched for these two rules.
  It fixed both after the feedback told it to look up the rules for member cards and badges (steps 11–13).
- Pure dense retrieval: exact-term queries (e.g. a document id like "SG-40") are not matched better than
  paraphrases. A BM25 component would help (see Task 3).
- Deprecated and active versions of a rule are very similar, so both are retrieved. We rely on the status line
  and the model to pick the active one.
- Each `write_site` sends the whole page; small fixes still cost a full page of output tokens.
- The step limit counts per round; a run with many feedback rounds can take more than 25 steps in total.
- Requires the gateway (university network/VPN). A network error after the client's retries ends the run.
