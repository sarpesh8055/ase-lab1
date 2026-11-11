"""Side experiments on dev (reported in the README; tuned on dev, so treat as exploratory):

1. Hybrid (R4) on different R3 chunk sizes.
2. Qwen3-embedding query instruction ("Instruct: ...\nQuery: ...") vs. plain question.

    uv run python task3_rag/experiments.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common.llm_client import LLMClient  # noqa: E402
from evaluate import evaluate  # noqa: E402
from retrieval import (CACHE, BM25Index, DenseIndex, embed_nocache, hybrid_scores, load_corpus,  # noqa: E402
                       load_jsonl, recursive_chunks, to_doc_ids, top_chunks)

INSTRUCT = "Instruct: Given a question about the PaderQueue message queue, retrieve documentation that answers it\nQuery: "


def fmt(rep):
    o, c = rep["overall"], rep["per_category"]
    return (f"recall {o['context_recall']:.3f} prec {o['context_precision']:.3f} | "
            + " ".join(f"{k[:5]} {v['context_recall']:.2f}" for k, v in c.items()))


def main():
    llm = LLMClient(log_path=HERE / "logs" / "experiments.jsonl")
    qs = load_jsonl(HERE / "data" / "questions_dev.jsonl")
    plain = np.load(CACHE / "queries_dev.npy").astype(np.float32)
    path = CACHE / "queries_dev_instruct.npy"
    if path.is_file():
        inst = np.load(path)
    else:
        inst = embed_nocache(llm, [INSTRUCT + q["question"] for q in qs], batch_size=16)
        np.save(path, inst)

    docs = load_corpus()
    out = {}
    for size in [64, 128, 256]:
        chunks = recursive_chunks(docs, size)
        dense = DenseIndex(llm, chunks, f"r3_rec{size}")
        bm25 = BM25Index(chunks)
        bm = [bm25.scores(q["question"]) for q in qs]
        for qname, qv in [("plain", plain), ("instruct", inst)]:
            for w in [None, 0.3, 0.4, 0.5, 0.6]:
                rows = []
                for i, q in enumerate(qs):
                    d = dense.scores(qv[i])
                    s = d if w is None else hybrid_scores(bm[i], d, w)
                    rows.append({"id": q["id"], "retrieved_doc_ids": to_doc_ids(top_chunks(s, chunks, 60))})
                rep = evaluate(rows, qs, 5)["summary"]
                name = f"size{size} {qname:<8} {'dense' if w is None else f'hybrid w={w}'}"
                out[name] = rep
                print(f"{name:<34} {fmt(rep)}")
    (HERE / "results" / "experiments.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
