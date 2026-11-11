# Manual check of 10 judge decisions (R5_hybrid_hyde)

Verdicts below were drafted with an AI assistant after checking each fact against `data/corpus.jsonl`. **Every group member must re-check them; change any you disagree with.**

Result: 8 agree, 1 disagree (dev030), 1 disagree on correctness / partly agree on faithfulness (dev025). The judge is reliable for single facts and abstentions. It is too strict and inconsistent on partially correct multi-hop answers (0 vs 0.5 for the same pattern), and answer relevance is meaningless for abstentions.

## dev008 (identifier)

- Question: In PaderQueue 4.x, what does `metrics.interval_s` default to?
- Ground truth: `10`
- Answer: `metrics.interval_s` defaults to `10` seconds in PaderQueue 4.x.
- Judge: correctness **1.0**, faithfulness 1.0, relevance 0.95 – It correctly states that `metrics.interval_s` defaults to 10 seconds.
- Claims: [{"claim": "In PaderQueue 4.x, `metrics.interval_s` defaults to 10 seconds.", "supported": true}]
- **Our verdict:** AGREE. Corpus page `metrics.interval_s` (4.x): default `10`, unit s, so "10 seconds" is right.

## dev061 (identifier)

- Question: What does the `--tenant` flag of `pq topic restore` do?
- Ground truth: Name of the tenant the command applies to.
- Answer: It specifies the name of the tenant the `pq topic restore` command applies to.
- Judge: correctness **1.0**, faithfulness 1.0, relevance 0.94 – It correctly states that the flag names the tenant the command applies to.
- Claims: [{"claim": "The `--tenant` flag specifies the name of the tenant the `pq topic restore` command applies to.", "supported": true}]
- **Our verdict:** AGREE. Same wording as the CLI reference.

## dev025 (multi-hop)

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2024-171?
- Ground truth: The incident was caused by PQ-E1915. Fix: Throttling protects the node. Add capacity or reduce load. As a last resort, raise `metrics.threshold_percent`.
- Answer: INC-2024-171 was caused by error PQ-E1915. The recommended permanent fix for PQ-E1915 is not included in the provided documentation excerpts.
- Judge: correctness **0.0**, faithfulness 0.5, relevance 0.62 – It says the permanent fix is not available, but the documentation recommends adding capacity or reducing load, with raising `metrics.threshold_percent` as a last resort.
- Claims: [{"claim": "INC-2024-171 was caused by error PQ-E1915.", "supported": false}, {"claim": "The recommended permanent fix for PQ-E1915 is not included in the provided documentation excerpts.", "supported": true}]
- **Our verdict:** DISAGREE (correctness). The answer gets the first hop right (PQ-E1915) and honestly says the fix is missing. By the judge's own rubric that is "partial" (0.5), and the judge gave 0.5 to the same pattern in dev083. Faithfulness 0.5: the judge marked "caused by PQ-E1915" unsupported; the report says the logs showed PQ-E1915 and names a failing disk as the trigger, so "caused by" is a slight over-claim. Debatable, we partly agree.

## dev030 (multi-hop)

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2025-175?
- Ground truth: The incident was caused by PQ-E2617. Fix: Check the logs for the underlying failure first. If the failures are transient, increase `dlq.max_retries`.
- Answer: Incident INC-2025-175 involved error PQ-E2617. The report directs readers to the error catalogue for the permanent fix, but that fix is not included in the documentation excerpts.
- Judge: correctness **0.0**, faithfulness 1.0, relevance 0.75 – It omits the recommended fix: check logs for the underlying failure and, if failures are transient, increase `dlq.max_retries`.
- Claims: [{"claim": "Incident INC-2025-175 involved error PQ-E2617.", "supported": true}, {"claim": "The report directs readers to the error catalogue for the permanent fix.", "supported": true}, {"claim": "The fix itself is not included in the documentation excerpts.", "supported": true}]
- **Our verdict:** DISAGREE. Same as dev025: first hop (PQ-E2617) correct, fix missing → should be 0.5, judged 0.

## dev004 (paraphrase)

- Question: Which setting controls how many times the mechanism that parks messages nobody could process tries again before it gives up?
- Ground truth: The setting `dlq.max_retries`.
- Answer: `scheduler.max_retries` controls how many times the scheduler retries releasing delayed messages before reporting the operation as failed.
- Judge: correctness **0.0**, faithfulness 1.0, relevance 0.71 – It names `scheduler.max_retries` for a different operation instead of the ground-truth setting `dlq.max_retries`.
- Claims: [{"claim": "`scheduler.max_retries` controls how many times the scheduler retries releasing delayed messages before reporting the operation as failed.", "supported": true}]
- **Our verdict:** AGREE. `scheduler.max_retries` is the wrong component (DLQ was asked). Faithful (it is in the context) but wrong: a good example that faithfulness ≠ correctness.

## dev011 (paraphrase)

- Question: Which setting controls how long the central process that receives and forwards all messages waits for an answer before it counts the attempt as failed?
- Ground truth: The setting `broker.timeout_ms`.
- Answer: `broker.timeout_ms` controls that wait; its default in PaderQueue 4.x is `10000` ms.
- Judge: correctness **1.0**, faithfulness 1.0, relevance 0.68 – It identifies `broker.timeout_ms` as the setting that controls the wait; the additional default value does not contradict the ground truth.
- Claims: [{"claim": "`broker.timeout_ms` controls how long the broker waits for a response before the operation fails.", "supported": true}, {"claim": "The default for `broker.timeout_ms` in PaderQueue 4.x is `10000` ms.", "supported": true}]
- **Our verdict:** AGREE. Default `10000` ms is on the `broker.timeout_ms` page; the extra detail is correct.

## dev013 (unanswerable)

- Question: What is the default value of `spool.queue_capacity`?
- Ground truth: The documentation does not contain this information.
- Answer: The documentation does not contain this information.
- Judge: correctness **1.0**, faithfulness None, relevance 0.41 – It clearly states that the documentation does not contain the information.
- Claims: []
- **Our verdict:** AGREE with correctness 1. The answer relevance of 0.41 is an artefact of the metric: questions generated from an abstention are about "what is not documented", far from the original question. Relevance is not meaningful for abstentions.

## dev054 (unanswerable)

- Question: What is the default value of `acktracker.worker_threads`?
- Ground truth: The documentation does not contain this information.
- Answer: The documentation does not contain this information.
- Judge: correctness **1.0**, faithfulness None, relevance 0.39 – It clearly states that the documentation does not contain the information.
- Claims: []
- **Our verdict:** AGREE (correctness). Same relevance artefact as dev013.

## dev009 (version)

- Question: What was the default value of `compactor.compression` in PaderQueue 2.x?
- Ground truth: `none`
- Answer: The default was `none`.
- Judge: correctness **1.0**, faithfulness 1.0, relevance 0.57 – It correctly states that the default value was `none`.
- Claims: [{"claim": "The default was `none`.", "supported": true}]
- **Our verdict:** AGREE.

## dev033 (version)

- Question: What was the default value of `spool.interval_s` in PaderQueue 3.x?
- Ground truth: `60`
- Answer: The default value of `spool.interval_s` in PaderQueue 3.x was `60` seconds.
- Judge: correctness **1.0**, faithfulness 1.0, relevance 0.96 – It gives the default value as 60 seconds, matching the ground truth.
- Claims: [{"claim": "The default value of `spool.interval_s` in PaderQueue 3.x was `60` seconds.", "supported": true}]
- **Our verdict:** AGREE. 3.x page: default `60`, unit s.
