# Task 3 – RAG under the microscope

Dataset, question format and the evaluation scripts are described in [DATASET.md](DATASET.md) (the original README of this folder).

## How to run

From the repository root (university network / VPN):

```bash
uv run python task3_rag/run_retrieval.py --sweep                         # R1–R5 on dev + test, metrics, weight sweep, summary.md
uv run python task3_rag/experiments.py                                   # side experiments (chunk size x hybrid, query instruction)
uv run python task3_rag/generate.py --config R5_hybrid_hyde --set dev --sample 50
uv run python task3_rag/generate.py --config R4_hybrid      --set dev --sample 50
uv run python task3_rag/judge.py task3_rag/results/answers_R5_hybrid_hyde_dev_s50.jsonl --sample 50 --out task3_rag/results/judge_R5_hybrid_hyde.jsonl
uv run python task3_rag/judge.py task3_rag/results/answers_R4_hybrid_dev_s50.jsonl      --sample 50 --out task3_rag/results/judge_R4_hybrid.jsonl
uv run python task3_rag/analyze.py R5_hybrid_hyde                        # failure classification + judge-check sheet
uv run python task3_rag/generate.py --config R5_hybrid_hyde --set test   # -> task3_rag/predictions_test.jsonl
uv run python task3_rag/evaluate.py task3_rag/results/retrieval_R5_hybrid_hyde_dev.jsonl --k 5
```

Embeddings, query vectors and HyDE passages are cached in `task3_rag/.cache/` (≈70 MB, **not submitted**;
a re-run rebuilds it, about 5 minutes).

| File | Content |
|---|---|
| `retrieval.py` | chunkers (fixed, recursive), identifier-aware BM25, dense index, min-max hybrid, HyDE, safe embedding |
| `run_retrieval.py` | runs R1–R5, writes `results/retrieval_*`, `metrics_*`, `summary.md`, `weight_sweep.json` |
| `experiments.py` | hybrid on all 3 chunk sizes, Qwen3 query instruction (`results/experiments.json`) |
| `generate.py` | answer generation (top-5 documents as context) |
| `analyze.py` | retrieval vs generation failure per wrong answer, judge-check sheet |
| `results/` | all outputs (JSONL / JSON / Markdown) |
| `predictions_test.jsonl` | test predictions of the best configuration (R5, whole-document context) |

## The configurations

All chunks start with a metadata header built from the corpus fields, e.g.
`[config] ingress.interval_s (PaderQueue 2.x) | version 2.x`. It is part of the embedded and the BM25-indexed text,
so a chunk still says which option/version/error it belongs to after it is cut out of its document.

| | Retrieval | Details |
|---|---|---|
| **R1** | BM25 (`rank_bm25.BM25Okapi`) on the R3 chunks (128) | identifier-aware tokenizer: `spool.buffer_bytes` → `spool.buffer_bytes, spool, buffer_bytes, buffer, bytes`; `PQ-E4663` → `pq-e4663, pq, e4663`; small stopword list |
| **R2** | fixed-size chunks + dense | windows of 128 tokens, overlap 32, inside each document |
| **R3** | recursive chunks + dense | a document that fits stays one chunk; otherwise split at headings → blank lines → lines → sentences, neighbours merged up to the size; a continued section repeats its heading. Sizes 64 / 128 / **256**, overlap 0 for all three |
| **R4** | hybrid of R1 + R3(128) | per query, BM25 and cosine scores are min-max normalised to [0, 1] over all chunks; `score = 0.5·dense + 0.5·bm25` |
| **R5** | R4 + **HyDE** | the chat model writes a hypothetical documentation passage for the question; the dense part uses the mean of the question and passage embeddings. BM25 still uses the original question |

Dense: `kiconnect.qwen3-embedding-8b` (gateway, 4096 dimensions), L2-normalised vectors in a numpy matrix.
Retrieval ranks the top 60 chunks; they are mapped to documents in rank order (duplicates removed), top 5 are evaluated.

## Retrieval results (dev, 120 answerable questions, k = 5)

Context **recall@5** (precision@5 in brackets):

| config | identifier | paraphrase | multi-hop | version | **overall** |
|---|---|---|---|---|---|
| R1 BM25 | **1.000** (0.79) | 0.367 (0.23) | 0.500 (0.83) | 0.700 (0.65) | 0.642 (0.62) |
| R2 fixed 128 + dense | 0.633 (0.55) | 0.833 (0.70) | 0.017 (0.02) | 0.833 (0.63) | 0.579 (0.47) |
| R3 recursive 64 + dense | 0.600 (0.54) | 0.833 (0.71) | 0.033 (0.04) | **1.000** (0.79) | 0.617 (0.52) |
| R3 recursive 128 + dense | 0.600 (0.49) | 0.900 (0.74) | 0.033 (0.05) | 0.800 (0.69) | 0.583 (0.49) |
| R3 recursive 256 + dense | 0.600 (0.52) | **0.933** (0.72) | 0.033 (0.02) | 0.733 (0.66) | 0.575 (0.48) |
| R4 hybrid (w = 0.5) | 0.900 (0.74) | 0.667 (0.49) | 0.500 (0.79) | 0.767 (0.67) | 0.708 (0.67) |
| R5 hybrid + HyDE | **1.000** (0.79) | 0.667 (0.53) | 0.500 (0.82) | 0.767 (0.67) | **0.733 (0.70)** |

Full numbers: `results/summary.md`, `results/metrics_<config>.json` (also per question).

### Which approach wins where, and why

- **identifier** (`retention.batch_size`, `PQ-E3441`, `pq snapshot describe --tenant`): BM25 is perfect. The identifier
  is one rare token in the index, so it gets a huge IDF weight. Dense embeddings blur `PQ-E3441` and `PQ-E3414`, or
  `spool.batch_size` and `retention.batch_size`: dense only gets 0.60.
- **paraphrase** ("the part that holds back messages until a later point in time" = scheduler): dense wins clearly
  (0.83–0.93 vs. 0.37). The question shares no words with the document, only the meaning.
- **multi-hop** ("the fix for the error that caused incident INC-2024-183"): no configuration gets more than 0.5.
  BM25 finds the incident report by its id (first hop). The error page needs the error code, which only appears *inside*
  the incident report, so a single retrieval with the question can't find it. Dense doesn't even find the first hop (0.03):
  incident ids like `INC-2024-183` look the same to the embedding model.
- **version** ("default of X in 2.x"): dense is better than BM25, because the version is in the header of every chunk and
  BM25 sees the 2.x, 3.x and 4.x page of an option as almost identical. Small chunks help most here (R3-64: 1.00), because the
  changelog line "X now defaults to … (previously …)" becomes its own chunk.
- **Hybrid** combines the two failure profiles: it keeps most of BM25's identifier and multi-hop results and gains on paraphrase.
  It is the best single setting overall, but in each category it is at or below the best component: a compromise, not a "best of both".

### Chunk size (R3: 64 / 128 / 256 tokens, overlap 0)

| size | chunks | avg tokens | recall@5 | precision@5 | best category |
|---|---|---|---|---|---|
| 64 | 3,444 | 57 | **0.617** | **0.519** | version 1.00 |
| 128 | 1,594 | 94 | 0.583 | 0.494 | |
| 256 | 968 | 141 | 0.575 | 0.479 | paraphrase 0.93 |

Most documents are short (median ~130 tokens), so at 256 almost every document is one chunk. Small chunks win on
version questions (a single changelog line can be matched), large chunks win on paraphrases (more context to match the meaning).
The differences overall are small (0.04 ≈ 5 questions).
We fixed 128 for R1/R4/R5 *before* running the comparison; `experiments.py` shows hybrid on 64/128/256 is within ±0.02.

### The hybrid weight

`results/weight_sweep.json` (dev, recall@5): w_dense = 0 → 0.642, 0.2 → 0.675, 0.4 → 0.683, **0.5 → 0.708**, 0.6 → 0.671,
0.8 → 0.592, 1.0 → 0.583. Above 0.6 multi-hop collapses (0.50 → 0.08) because the incident report drops out of the top 5;
below 0.4 paraphrase drops back to BM25 level. We use **w = 0.5**: it is the peak of the sweep, and it is the
neutral choice (equal weight after normalisation), so we are not tuning on noise. Note: the sweep is on dev, the same set we report on;
the test predictions are the only held-out evaluation.

### Why HyDE for R5

The weak spot of R4 is the paraphrase / identifier trade-off in the dense part. HyDE turns the question into a passage in the
style of the documentation ("Set `scheduler.max_connections` …"), which is closer to the documents in embedding space.
Result: identifier 0.90 → 1.00, overall 0.708 → 0.733, paraphrase unchanged. It costs one LLM call per query.
HyDE can't help multi-hop: the model invents an error code rather than knowing the one in the incident report.
Example of a wrong guess: for dev004 ("mechanism that parks messages nobody could process" = DLQ) HyDE wrote
"Set `parking.maxRetries` …", so this paraphrase is still missed.

### Side experiment: query instruction for Qwen3

Qwen3-embedding is trained with an instruction prefix for queries. With
`Instruct: Given a question about the PaderQueue message queue, retrieve documentation that answers it\nQuery: …`
dense R3-128 goes 0.583 → 0.613, hybrid R3-128 0.708 → 0.742 (`results/experiments.json`). We found this after fixing the
configurations, so it is not used in R1–R5; it is the first thing we would add.

## Cost and latency

| config | chunks | indexing (embedding, first run) | latency per query (median) | LLM tokens per query (retrieval) | context tokens (5 chunks) |
|---|---|---|---|---|---|
| R1 BM25 | 1,594 | 0.4 s (BM25 build) | **16 ms** | 0 | 463 |
| R2 fixed 128 | 1,327 | 29 s | 177 ms | 0 | 603 |
| R3 rec 64 | 3,444 | 60 s | 181 ms | 0 | 290 |
| R3 rec 128 | 1,594 | 43 s | 178 ms | 0 | 436 |
| R3 rec 256 | 968 | 19 s | 174 ms | 0 | 710 |
| R4 hybrid | 1,594 | 43 s + 0.4 s | 177 ms | 0 | 466 |
| R5 hybrid + HyDE | 1,594 | 43 s + 0.4 s | **≈ 6.3 s** | ≈ 105 in + 310 out | 476 |

- Dense latency is dominated by the query embedding call to the gateway (~170 ms); scoring 1,594 × 4096 in numpy takes < 2 ms.
  The p95 is ~1.5 s, because the gateway rate limit (100 requests/min) hit while we embedded the queries one by one.
- R5: the median HyDE call takes 6.2 s (gpt-6-luna is a reasoning model; ~310 output tokens including hidden reasoning).
  `summary.md` shows 1.8 s for R5 because the passages were generated with 4 parallel threads (wall time / n); the real
  latency per query is ~6.3 s. Cost: $0.046 for 280 HyDE calls ≈ **$0.00016 per query**.
- Generation (both best configs): ~1,060 prompt tokens and ~50 output tokens per question, median 2.7 s, ≈ $0.00015 per question.
- Embedding the corpus is free (gateway embedding model). The whole Task 3 cost < $0.30.

## A gateway bug we found (and why our first numbers were wrong)

Our first run gave dense recall of 0.05 for 256-token chunks: nonsense. A check (embed a text alone, compare with its vector
from a batch) showed that vectors from a batch belonged to *other* texts. Cause: the gateway caches embeddings **per text**. When a batch
contains texts that are cached and texts that are not, the result comes back in the wrong order (we reproduced it with 16 synthetic
sentences: half cached → wrong vectors; same batch with the cache disabled → correct).
Fix (`retrieval.embed_nocache` / `embed_verified`): send `{"cache": {"no-cache": true}}` with embedding requests and verify 5
random vectors against single calls before an index is used. (Task 2 was not affected: all its texts were new in one batch;
we verified it the same way.)

## End-to-end evaluation (judge.py, stratified 50 dev questions)

Answers: top-5 documents of the configuration as context, `openai.gpt-6-luna`, prompt in `generate.py`
(answer only from the excerpts, exact abstention sentence, prefer reference pages over forum posts, mind versions).

We ran it twice. **v1** gave the generator the best-matching *chunk* of each top-5 document. The failure analysis
showed 3 generation failures in identifier questions: the right error page was retrieved, but its best chunk ended at
"Common causes", and the "How to fix" section was in the next chunk, so the model correctly said it can't find the fix.
**v2** ranks with chunks but gives the generator the *whole* document (small-to-big; documents > 400 tokens, i.e. changelogs,
contribute only their retrieved chunks). Retrieval is identical in v1 and v2.

| config | context | n | abstained | faithfulness | answer relevance | **correctness** |
|---|---|---|---|---|---|---|
| R5 hybrid + HyDE | v1 chunk | 50 | 0.38 | 0.976 | 0.624 | 0.66 |
| R4 hybrid | v1 chunk | 50 | 0.34 | 0.975 | 0.638 | 0.68 |
| R5 hybrid + HyDE | **v2 doc** | 50 | 0.32 | 0.971 | 0.616 | **0.75** |
| R4 hybrid | **v2 doc** | 50 | 0.32 | 0.985 | 0.628 | **0.75** |

Per category (v2):

| category | correctness R5 | correctness R4 | faithfulness R5 / R4 | abstained |
|---|---|---|---|---|
| identifier | 1.00 | 1.00 | 1.00 / 1.00 | 0.0 |
| paraphrase | 0.80 | 0.80 | 1.00 / 1.00 | 0.1 |
| version | 0.90 | 0.90 | 1.00 / 1.00 | 0.1 |
| multi-hop | 0.05 | 0.05 | 0.83 / 0.92 | 0.4 |
| unanswerable | 1.00 | 1.00 | – | 1.0 |

Identifier correctness went 0.70 → 1.00 from v1 to v2 (R5). Files: `results/answers_*_dev_s50[_chunkctx].jsonl`,
`results/judge_*[_chunkctx].jsonl`, judge logs in `task3_rag/logs/`.

- Faithfulness is 0.97–0.99: the generator almost never invents facts. When it is wrong, it is wrong *with* the context
  (it names a setting that is in the context but belongs to another component).
- All 10 unanswerable questions get the abstention sentence. The flip side: on multi-hop the model abstains, or says
  "the fix is not in the excerpts", when the second document is missing. That is honest, but scores 0.
- R5 and R4 have the same correctness on this sample, although R5 has better retrieval recall (0.733 vs 0.708):
  the difference is 3 identifier questions in the whole dev set, and the sample contains only one of them.

### Do we trust the judge? (10 decisions checked by hand: `results/judge_check_R5_hybrid_hyde.md`)

We agree with 8 of 10. Disagreements: two multi-hop answers that found the first hop (the error code) and said that the fix
is missing got correctness 0, while the same pattern got 0.5 elsewhere (dev083), and the judge's own rubric calls that "partial".
The judge is reliable for single facts and abstentions, but strict and inconsistent for partial answers. Answer relevance
is not meaningful for abstentions (0.40 for a correct abstention), so we don't use it to compare configurations.

## Failure analysis (R5, v2, judged sample)

13 of 50 answers are not fully correct: **10 partial retrieval** failures (multi-hop: one of the two needed documents is missing),
**3 retrieval** failures, **0 generation** failures (after v2; v1 had 3). Full list: `results/failures_R5_hybrid_hyde.md`.
Five representative cases:

1. **dev025, multi-hop – retrieval (second hop).** "Permanent fix for the error that caused INC-2024-171?" Top-5 = the incident report
   plus 4 *other* incident reports (they share the words "incident", "permanent fix", "error catalogue"). The report names PQ-E1915,
   but the error page for PQ-E1915 can't be found with the words of the question. The generator does the right thing ("caused by PQ-E1915,
   the fix is not in the excerpts"). One-shot retrieval can't solve this; it needs a second retrieval step with the code from the first document.
2. **dev042, multi-hop (other pattern) – retrieval (second hop) + a generation choice.** "Current default of the setting that the error
   catalogue recommends changing for PQ-E2051?" The error page *is* retrieved (rank 5, behind a forum thread and 3 incident reports that mention
   PQ-E2051) and names `compactor.compression`, but the config page with the default is not retrieved. The model abstains completely
   instead of saying "the setting is `compactor.compression`; its default is not in the excerpts". Our prompt pushes it towards abstaining.
3. **dev004, paraphrase – retrieval.** "The mechanism that parks messages nobody could process" = the dead-letter queue (`dlq.max_retries`).
   BM25 has no shared words, and the embedding model doesn't connect "parks unprocessable messages" with "DLQ". HyDE invented
   `parking.maxRetries`. The context contained `spool.max_retries`, `scheduler.max_retries`, …, and the model picked a wrong but
   plausible one: faithful to the context, still wrong.
4. **dev101, version – retrieval.** "In which release did the default of `auth.interval_s` change?" The answer is one line of the 3.0 release notes.
   Top-5: the 2.x config page and **4 forum threads titled "What does auth.interval_s do?"**. The threads repeat the identifier, so BM25 ranks them high,
   and they push the changelog out of the top 5. The model abstains (correct behaviour for that context).
5. **dev087, paraphrase – retrieval.** "Setting that limits how many clients can talk to the part that holds back messages until later
   (= scheduler) in parallel" → `scheduler.max_connections`. Retrieved: `pq tenant move`, two changelogs, `quota.batch_size`: unrelated.
   The paraphrase is two steps away from the document (scheduler, "max connections"), and the BM25 half of the hybrid adds noise
   from generic words ("messages", "clients", "parallel").

**Pattern:** every remaining failure starts in retrieval. Multi-hop is the biggest block (10 of 13); about 0.5 recall is the ceiling for
single-shot retrieval in this category. Forum threads are the main source of noise for version questions.

## Recommendation

For deployment we recommend **R4 (hybrid BM25 + dense, w = 0.5, recursive 128-token chunks with metadata headers) with whole-document context (v2)**:

- Same end-to-end correctness as R5 on the judged sample (0.75); retrieval recall only 0.025 lower.
- About 180 ms per query and no LLM call for retrieval, vs. about 6.3 s and an extra LLM call per query with HyDE (35× slower).
  HyDE's only gain is on identifiers, where BM25 is already strong.
- BM25 is essential (identifiers, incident ids) and dense is essential (paraphrases); neither alone is acceptable (0.64 / 0.58).

Next steps, by expected gain: (1) **two-step retrieval for multi-hop**: extract error codes / option names from the first top-5
and search again (targets 10 of the 13 remaining failures); (2) the Qwen3 query instruction (+0.03 recall, free);
(3) down-weight forum threads, or deduplicate threads with the same title; (4) let the generator give the partial answer instead of abstaining.

For the **test predictions** we used R5 (v2 context): the test set is graded on recall@5 of the retrieved documents, where R5 is our
best configuration (dev recall@5 0.733 vs. 0.642 for the R1 baseline).

## Known limitations

- The weight, chunk size and prompts were chosen on dev; the judged sample is only 50 questions (10 per category), so differences
  in correctness below about 0.1 are not significant.
- Latencies were measured from one laptop through the gateway; the p95 includes waits caused by the gateway rate limit.
- The LLM log of parallel runs (HyDE and generation use 4 threads) can contain an interleaved line; our scripts skip unreadable lines.
- The judge is the same model as the generator (gpt-6-luna), which may favour its own style.

## Cost

All of Task 3 (HyDE for 250 questions, 350 generated answers, 4 judge runs) cost **about $0.15** (sum of `cost_usd` in the logs).
Embeddings are free.
