# Retrieval results (dev, k=5)

## Context recall@5 per category

| config | identifier | paraphrase | multi-hop | version | overall recall | overall precision |
|---|---|---|---|---|---|---|
| R1_bm25 | 1.000 | 0.367 | 0.500 | 0.700 | **0.642** | 0.623 |
| R2_fixed128 | 0.633 | 0.833 | 0.017 | 0.833 | **0.579** | 0.473 |
| R3_rec64 | 0.600 | 0.833 | 0.033 | 1.000 | **0.617** | 0.519 |
| R3_rec128 | 0.600 | 0.900 | 0.033 | 0.800 | **0.583** | 0.494 |
| R3_rec256 | 0.600 | 0.933 | 0.033 | 0.733 | **0.575** | 0.479 |
| R4_hybrid | 0.900 | 0.667 | 0.500 | 0.767 | **0.708** | 0.672 |
| R5_hybrid_hyde | 1.000 | 0.667 | 0.500 | 0.767 | **0.733** | 0.700 |

## Context precision@5 per category

| config | identifier | paraphrase | multi-hop | version |
|---|---|---|---|---|
| R1_bm25 | 0.787 | 0.225 | 0.831 | 0.648 |
| R2_fixed128 | 0.550 | 0.700 | 0.017 | 0.626 |
| R3_rec64 | 0.536 | 0.711 | 0.042 | 0.786 |
| R3_rec128 | 0.494 | 0.736 | 0.050 | 0.694 |
| R3_rec256 | 0.517 | 0.722 | 0.015 | 0.662 |
| R4_hybrid | 0.744 | 0.488 | 0.787 | 0.668 |
| R5_hybrid_hyde | 0.786 | 0.530 | 0.815 | 0.668 |

## Cost and latency

| config | chunks | avg chunk tokens | indexing: embedding s (first run) | BM25 build s | latency ms median / p95 | LLM tokens per query (retrieval) | context tokens (top-5 chunks) |
|---|---|---|---|---|---|---|---|
| R1_bm25 | 1594 | 94 | 0.0 | 0.39 | 15.6 / 19.0 | 0 | 463 |
| R2_fixed128 | 1327 | 117 | 29.4 | 0.0 | 177.0 / 1506.5 | 0 | 603 |
| R3_rec64 | 3444 | 57 | 59.7 | 0.0 | 181.3 / 1504.3 | 0 | 290 |
| R3_rec128 | 1594 | 94 | 42.9 | 0.0 | 177.5 / 1506.0 | 0 | 436 |
| R3_rec256 | 968 | 141 | 19.1 | 0.0 | 174.0 / 1506.8 | 0 | 710 |
| R4_hybrid | 1594 | 94 | 42.9 | 0.39 | 177.0 / 1507.5 | 0 | 466 |
| R5_hybrid_hyde | 1594 | 94 | 42.9 | 0.39 | 1783.4 / 3114.1 | 152 | 476 |
