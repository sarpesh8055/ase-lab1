# Failures of R5_hybrid_hyde on the judged dev sample (correctness < 1)

Counts: {'retrieval': 3, 'generation': 0, 'partial retrieval': 10}

## dev004 (paraphrase) – correctness 0.0 – **retrieval failure**

- Question: Which setting controls how many times the mechanism that parks messages nobody could process tries again before it gives up?
- Ground truth: The setting `dlq.max_retries`.
- Answer: `scheduler.max_retries` controls how many times the scheduler retries releasing delayed messages before reporting the operation as failed.
- Needed (groups): [['d0032 (config: dlq.max_retries)', 'd0303 (config: dlq.max_retries (PaderQueue 3.x))']]
- Retrieved top-5: ['d0806 (error: PQ-E2995 QUOTA_RETRIES_EXHAUSTED)', 'd0406 (changelog: PaderQueue 3.0 release notes)', 'd0655 (config: spool.max_retries)', 'd0398 (config: spool.max_retries (PaderQueue 3.x))', 'd0793 (forum: What does spool.max_retries do?)']
- Judge: It names `scheduler.max_retries` for a different operation instead of the ground-truth setting `dlq.max_retries`.

## dev025 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2024-171?
- Ground truth: The incident was caused by PQ-E1915. Fix: Throttling protects the node. Add capacity or reduce load. As a last resort, raise `metrics.threshold_percent`.
- Answer: INC-2024-171 was caused by error PQ-E1915. The recommended permanent fix for PQ-E1915 is not included in the provided documentation excerpts.
- Needed (groups): [['d0253 (incident: Postmortem INC-2024-171)'], ['d0183 (error: PQ-E1915 METRICS_THROTTLED)']]
- Retrieved top-5: ['d0253 (incident: Postmortem INC-2024-171)', 'd0602 (incident: Postmortem INC-2024-166)', 'd0729 (incident: Postmortem INC-2024-135)', 'd0384 (incident: Postmortem INC-2024-128)', 'd0391 (incident: Postmortem INC-2025-116)']
- Judge: It says the permanent fix is not available, but the documentation recommends adding capacity or reducing load, with raising `metrics.threshold_percent` as a last resort.

## dev030 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2025-175?
- Ground truth: The incident was caused by PQ-E2617. Fix: Check the logs for the underlying failure first. If the failures are transient, increase `dlq.max_retries`.
- Answer: Incident INC-2025-175 involved error PQ-E2617. The report directs readers to the error catalogue for the permanent fix, but that fix is not included in the documentation excerpts.
- Needed (groups): [['d0442 (incident: Postmortem INC-2025-175)'], ['d0174 (error: PQ-E2617 DLQ_RETRIES_EXHAUSTED)']]
- Retrieved top-5: ['d0442 (incident: Postmortem INC-2025-175)', 'd0460 (incident: Postmortem INC-2025-145)', 'd0197 (incident: Postmortem INC-2025-198)', 'd0261 (incident: Postmortem INC-2025-182)', 'd0488 (incident: Postmortem INC-2025-190)']
- Judge: It omits the recommended fix: check logs for the underlying failure and, if failures are transient, increase `dlq.max_retries`.

## dev032 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2024-213?
- Ground truth: The incident was caused by PQ-E3891. Fix: Add worker threads or increase `compactor.queue_capacity`. A queue that stays full usually means the component is too slow.
- Answer: Incident INC-2024-213 involved error PQ-E3891. The excerpts do not include the error catalogue’s recommended permanent fix.
- Needed (groups): [['d0377 (incident: Postmortem INC-2024-213)'], ['d0350 (error: PQ-E3891 COMPACTOR_WORK_QUEUE_FULL)']]
- Retrieved top-5: ['d0377 (incident: Postmortem INC-2024-213)', 'd0602 (incident: Postmortem INC-2024-166)', 'd0384 (incident: Postmortem INC-2024-128)', 'd0729 (incident: Postmortem INC-2024-135)', 'd0488 (incident: Postmortem INC-2025-190)']
- Judge: It identifies PQ-E3891 but omits the documented fix: add worker threads or increase `compactor.queue_capacity`.

## dev042 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: What is the current default value of the setting that the error catalogue recommends changing for PQ-E2051?
- Ground truth: `compactor.compression` defaults to `lz4` in 4.x.
- Answer: The documentation does not contain this information.
- Needed (groups): [['d0738 (error: PQ-E2051 COMPACTOR_CODEC_MISMATCH)'], ['d0564 (config: compactor.compression)']]
- Retrieved top-5: ['d0785 (forum: PQ-E2051 after upgrade?)', 'd0324 (incident: Postmortem INC-2025-169)', 'd0048 (incident: Postmortem INC-2024-185)', 'd0644 (incident: Postmortem INC-2024-200)', 'd0738 (error: PQ-E2051 COMPACTOR_CODEC_MISMATCH)']
- Judge: It says the information is unavailable, but the current default is `lz4` for `compactor.compression` in 4.x.

## dev047 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: What is the current default value of the setting that the error catalogue recommends changing for PQ-E2425?
- Ground truth: `acktracker.max_retries` defaults to `20` in 4.x.
- Answer: The documentation does not contain this information.
- Needed (groups): [['d0522 (error: PQ-E2425 ACKTRACKER_RETRIES_EXHAUSTED)'], ['d0749 (config: acktracker.max_retries)']]
- Retrieved top-5: ['d0517 (forum: PQ-E2425 after upgrade?)', 'd0576 (forum: PQ-E2425 after upgrade?)', 'd0522 (error: PQ-E2425 ACKTRACKER_RETRIES_EXHAUSTED)', 'd0805 (changelog: PaderQueue 2.1 release notes)', "d0116 (forum: Getting 'acktracker: retries exhausted' all the time)"]
- Judge: It says the information is unavailable, but the default is `20` in 4.x.

## dev065 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2025-101?
- Ground truth: The incident was caused by PQ-E3177. Fix: Check for connection leaks in clients (connections that are never closed). If the load is legitimate, increase `scheduler.max_connections`.
- Answer: Incident INC-2025-101 was associated with error PQ-E3177. The documentation excerpts do not include the error catalogue’s recommended permanent fix for PQ-E3177.
- Needed (groups): [['d0919 (incident: Postmortem INC-2025-101)'], ['d0227 (error: PQ-E3177 SCHEDULER_CONNECTION_LIMIT_REACHED)']]
- Retrieved top-5: ['d0919 (incident: Postmortem INC-2025-101)', 'd0460 (incident: Postmortem INC-2025-145)', 'd0197 (incident: Postmortem INC-2025-198)', 'd0488 (incident: Postmortem INC-2025-190)', 'd0261 (incident: Postmortem INC-2025-182)']
- Judge: It says the recommended fix is unavailable, but the documentation recommends checking for client connection leaks and increasing `scheduler.max_connections` if the load is legitimate.

## dev069 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: What is the current default value of the setting that the error catalogue recommends changing for PQ-E4020?
- Ground truth: `spool.compression` defaults to `lz4` in 4.x.
- Answer: The documentation does not contain this information.
- Needed (groups): [['d0506 (error: PQ-E4020 SPOOL_CODEC_MISMATCH)'], ['d0679 (config: spool.compression)']]
- Retrieved top-5: ['d0237 (forum: PQ-E4020 after upgrade?)', 'd0510 (forum: PQ-E4020 after upgrade?)', 'd0506 (error: PQ-E4020 SPOOL_CODEC_MISMATCH)', 'd0110 (incident: Postmortem INC-2025-129)', 'd0769 (forum: Help: spool: codec mismatch in production)']
- Judge: It says the documentation lacks the information, but the current default is `lz4` for `spool.compression` in 4.x.

## dev083 (multi-hop) – correctness 0.5 – **partial retrieval failure**

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2024-147?
- Ground truth: The incident was caused by PQ-E2051. Fix: Set `compactor.compression` to the same value on all nodes, then restart them one after another.
- Answer: INC-2024-147 showed error PQ-E2051. The incident report says to apply the error catalogue’s recommended fix, but the excerpts do not specify what that fix is.
- Needed (groups): [['d0786 (incident: Postmortem INC-2024-147)'], ['d0738 (error: PQ-E2051 COMPACTOR_CODEC_MISMATCH)']]
- Retrieved top-5: ['d0786 (incident: Postmortem INC-2024-147)', 'd0602 (incident: Postmortem INC-2024-166)', 'd0384 (incident: Postmortem INC-2024-128)', 'd0729 (incident: Postmortem INC-2024-135)', 'd0391 (incident: Postmortem INC-2025-116)']
- Judge: It correctly identifies PQ-E2051 but omits the recommended fix and incorrectly says the excerpts do not specify it.

## dev087 (paraphrase) – correctness 0.0 – **retrieval failure**

- Question: Which setting limits how many clients can talk to the part that holds back messages until a later point in time in parallel?
- Ground truth: The setting `scheduler.max_connections`.
- Answer: The documentation does not contain this information.
- Needed (groups): [['d0153 (config: scheduler.max_connections)']]
- Retrieved top-5: ['d0059 (cli: pq tenant move)', 'd0507 (changelog: PaderQueue 1.1 release notes)', 'd0221 (cli: pq dlq create)', 'd0036 (config: quota.batch_size)', 'd0192 (changelog: PaderQueue 2.0 release notes)']
- Judge: It says the information is unavailable, but the setting is `scheduler.max_connections`.

## dev089 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: Which permanent fix does the documentation recommend for the error that caused incident INC-2024-166?
- Ground truth: The incident was caused by PQ-E4013. Fix: Throttling protects the node. Add capacity or reduce load. As a last resort, raise `auth.threshold_percent`.
- Answer: INC-2024-166 was caused by PQ-E4013. The documentation excerpts do not include the error catalogue’s recommended permanent fix for PQ-E4013.
- Needed (groups): [['d0602 (incident: Postmortem INC-2024-166)'], ['d0229 (error: PQ-E4013 AUTH_THROTTLED)']]
- Retrieved top-5: ['d0602 (incident: Postmortem INC-2024-166)', 'd0384 (incident: Postmortem INC-2024-128)', 'd0729 (incident: Postmortem INC-2024-135)', 'd0488 (incident: Postmortem INC-2025-190)', 'd0391 (incident: Postmortem INC-2025-116)']
- Judge: It says the recommended fix is unavailable and omits the documented guidance to add capacity or reduce load, with raising `auth.threshold_percent` as a last resort.

## dev101 (version) – correctness 0.0 – **retrieval failure**

- Question: In which release did the default of `auth.interval_s` change, and what was it before?
- Ground truth: In 3.0; before it was `10`.
- Answer: The documentation does not contain this information.
- Needed (groups): [['d0406 (changelog: PaderQueue 3.0 release notes)']]
- Retrieved top-5: ['d0895 (config: auth.interval_s (PaderQueue 2.x))', 'd0693 (forum: What does auth.interval_s do?)', 'd0875 (forum: What does auth.interval_s do?)', 'd0273 (forum: What does auth.interval_s do?)', 'd0142 (forum: What does auth.interval_s do?)']
- Judge: It says the information is unavailable, but the ground truth states the default changed in release 3.0 and was previously 10.

## dev119 (multi-hop) – correctness 0.0 – **partial retrieval failure**

- Question: What is the current default value of the setting that the error catalogue recommends changing for PQ-E1799?
- Ground truth: `retention.threshold_percent` defaults to `95` in 4.x.
- Answer: The documentation does not contain this information.
- Needed (groups): [['d0649 (error: PQ-E1799 RETENTION_THROTTLED)'], ['d0365 (config: retention.threshold_percent)']]
- Retrieved top-5: ['d0712 (forum: PQ-E1799 after upgrade?)', 'd0649 (error: PQ-E1799 RETENTION_THROTTLED)', "d0019 (forum: Getting 'retention: throttled' all the time)", "d0336 (forum: Getting 'retention: throttled' all the time)", "d0589 (forum: Getting 'retention: throttled' all the time)"]
- Judge: The answer says the information is unavailable, but the ground truth states that `retention.threshold_percent` defaults to `95` in 4.x.
