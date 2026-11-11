"""Runs all retrieval configurations on the dev (and test) questions and evaluates them.

    uv run python task3_rag/run_retrieval.py              # everything
    uv run python task3_rag/run_retrieval.py --sweep      # also the hybrid weight sweep

Writes to task3_rag/results/:
    retrieval_<cfg>_dev.jsonl / _test.jsonl   ranked doc ids per question (input for evaluate.py)
    metrics_<cfg>.json                        evaluate.py output (overall + per category + per question)
    summary.md / summary.json                 tables: configs x categories, chunk sizes, cost/latency
    weight_sweep.json                         recall/precision of R4 for w_dense in 0.0 .. 1.0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common.llm_client import LLMClient  # noqa: E402
from evaluate import evaluate  # noqa: E402
from retrieval import (CACHE, BM25Index, embed_verified, DenseIndex, _normalise, fixed_chunks, hybrid_scores,  # noqa: E402
                       hyde_passages, load_corpus, load_jsonl, n_tokens, recursive_chunks, top_chunks, to_doc_ids)

RESULTS = HERE / "results"
DATA = HERE / "data"
K = 5
N_CANDIDATE_CHUNKS = 60   # chunks ranked per query before mapping to documents

# --- settings (chosen as described in the README) ---
R2_SIZE, R2_OVERLAP = 128, 32
R3_SIZES = [64, 128, 256]
R3_SIZE = 128             # chunk size used by R1, R3, R4, R5 (best of R3_SIZES, see summary.md)
W_DENSE = 0.5             # hybrid weight of the dense score (see weight sweep in README)


def embed_queries(llm, questions: list[dict], tag: str) -> tuple[np.ndarray, list[float]]:
    """One embedding call per query, so we can measure per-query latency. Cached (vectors + timings)."""
    path_v, path_t = CACHE / f"queries_{tag}.npy", CACHE / f"queries_{tag}_latency.json"
    if path_v.is_file() and path_t.is_file():
        return np.load(path_v).astype(np.float32), json.loads(path_t.read_text())
    vecs, times = [], []
    for q in questions:
        start = time.time()
        vecs.append(llm.embed([q["question"]])[0])
        times.append(time.time() - start)
    vecs = _normalise(np.asarray(vecs, dtype=np.float32))
    CACHE.mkdir(exist_ok=True)
    np.save(path_v, vecs)
    path_t.write_text(json.dumps(times))
    return vecs, times


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class Runner:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.docs = load_corpus()
        self.sets = {"dev": load_jsonl(DATA / "questions_dev.jsonl"), "test": load_jsonl(DATA / "questions_test.jsonl")}
        self.qvec, self.qlat = {}, {}
        for name, qs in self.sets.items():
            self.qvec[name], self.qlat[name] = embed_queries(llm, qs, name)
        self.stats: dict[str, dict] = {}
        self.metrics: dict[str, dict] = {}

    # ---------------------------------------------------------------- indexes

    def build_dense(self, name: str, chunker, **kw):
        start = time.time()
        chunks = chunker(self.docs, **kw)
        chunk_s = time.time() - start
        index = DenseIndex(self.llm, chunks, name)
        return chunks, index, chunk_s

    # ---------------------------------------------------------------- one configuration

    def run_config(self, cfg: str, ranker, chunks, index_info: dict, extra_query_tokens=None, extra_latency=None):
        """ranker(set_name, i) -> score vector over `chunks`."""
        lat_all = []
        for set_name, qs in self.sets.items():
            rows = []
            for i, q in enumerate(qs):
                start = time.time()
                scores = ranker(set_name, i)
                ranked = top_chunks(scores, chunks, N_CANDIDATE_CHUNKS)
                score_s = time.time() - start
                if set_name == "dev":
                    lat = score_s + (self.qlat[set_name][i] if index_info.get("dense") else 0.0)
                    lat += extra_latency[set_name][i] if extra_latency else 0.0
                    lat_all.append(lat)
                rows.append({"id": q["id"], "retrieved_doc_ids": to_doc_ids(ranked)[:20],
                             "retrieved_chunk_ids": [c.chunk_id for c, _ in ranked[:20]]})
            write_jsonl(RESULTS / f"retrieval_{cfg}_{set_name}.jsonl", rows)

        report = evaluate(load_jsonl(RESULTS / f"retrieval_{cfg}_dev.jsonl"), self.sets["dev"], K)
        (RESULTS / f"metrics_{cfg}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.metrics[cfg] = report["summary"]

        # tokens per query: question (+ HyDE prompt/answer) for retrieval, + top-5 chunks for generation
        dev_rows = load_jsonl(RESULTS / f"retrieval_{cfg}_dev.jsonl")
        by_id = {c.chunk_id: c for c in chunks}
        ctx_tokens = []
        for r in dev_rows:
            seen, toks = set(), 0
            for cid in r["retrieved_chunk_ids"]:
                c = by_id[cid]
                if c.doc_id in seen:
                    continue
                seen.add(c.doc_id)
                toks += n_tokens(c.text)
                if len(seen) == K:
                    break
            ctx_tokens.append(toks)
        q_tokens = [n_tokens(q["question"]) for q in self.sets["dev"]]
        self.stats[cfg] = {
            **index_info,
            "latency_ms_median": round(1000 * float(np.median(lat_all)), 1),
            "latency_ms_p95": round(1000 * float(np.percentile(lat_all, 95)), 1),
            "retrieval_llm_tokens_per_query": round(float(np.mean(extra_query_tokens)), 0) if extra_query_tokens else 0,
            "embedded_tokens_per_query": round(float(np.mean(q_tokens)) + (index_info.get("hyde_tokens", 0) or 0), 0)
            if index_info.get("dense") else 0,
            "context_tokens_top5": round(float(np.mean(ctx_tokens)), 0),
        }
        o = report["summary"]["overall"]
        print(f"{cfg:<14} recall@5 {o['context_recall']:.3f}  precision@5 {o['context_precision']:.3f}  "
              f"latency {self.stats[cfg]['latency_ms_median']} ms")


def index_info(chunks, index=None, chunk_s=0.0, bm25_s=0.0, dense=False) -> dict:
    return {"n_chunks": len(chunks), "avg_chunk_tokens": round(float(np.mean([n_tokens(c.text) for c in chunks])), 0),
            "dense": dense, "chunking_s": round(chunk_s, 2), "bm25_build_s": round(bm25_s, 2),
            "embedding_s": round(index.embed_seconds, 1) if index is not None else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true", help="hybrid weight sweep on dev")
    args = parser.parse_args()

    llm = LLMClient(log_path=HERE / "logs" / "retrieval.jsonl")
    run = Runner(llm)
    timings_path = CACHE / "index_timings.json"   # first-run embedding times survive the cache
    timings = json.loads(timings_path.read_text()) if timings_path.is_file() else {}

    def remember(name, info):
        if info["embedding_s"] > 0:
            timings[name] = info["embedding_s"]
            timings_path.write_text(json.dumps(timings, indent=1))
        info["embedding_s"] = timings.get(name, info["embedding_s"])
        return info

    # ---- R2: fixed-size + dense
    chunks, idx, cs = run.build_dense("r2_fixed", fixed_chunks, size=R2_SIZE, overlap=R2_OVERLAP)
    run.run_config("R2_fixed128", lambda s, i, idx=idx: idx.scores(run.qvec[s][i]), chunks,
                   remember("r2", index_info(chunks, idx, cs, dense=True)))

    # ---- R3: recursive + dense, three chunk sizes
    r3 = {}
    for size in R3_SIZES:
        chunks, idx, cs = run.build_dense(f"r3_rec{size}", recursive_chunks, size=size)
        r3[size] = (chunks, idx)
        run.run_config(f"R3_rec{size}", lambda s, i, idx=idx: idx.scores(run.qvec[s][i]), chunks,
                       remember(f"r3_{size}", index_info(chunks, idx, cs, dense=True)))
    chunks, dense = r3[R3_SIZE]

    # ---- R1: BM25 on the R3 chunks
    start = time.time()
    bm25 = BM25Index(chunks)
    bm25_s = time.time() - start
    bm25_cache = {s: [None] * len(qs) for s, qs in run.sets.items()}

    def bm25_scores(s, i):
        if bm25_cache[s][i] is None:
            bm25_cache[s][i] = bm25.scores(run.sets[s][i]["question"])
        return bm25_cache[s][i]

    run.run_config("R1_bm25", lambda s, i: bm25.scores(run.sets[s][i]["question"]), chunks,
                   index_info(chunks, None, 0, bm25_s))

    # ---- R4: hybrid
    if args.sweep:
        sweep = {}
        for w in [round(x, 1) for x in np.arange(0, 1.01, 0.1)]:
            rows = [{"id": q["id"], "retrieved_doc_ids": to_doc_ids(top_chunks(
                hybrid_scores(bm25_scores("dev", i), dense.scores(run.qvec["dev"][i]), w), chunks, N_CANDIDATE_CHUNKS))}
                for i, q in enumerate(run.sets["dev"])]
            rep = evaluate(rows, run.sets["dev"], K)["summary"]
            sweep[w] = {"overall": rep["overall"],
                        "per_category": {c: v["context_recall"] for c, v in rep["per_category"].items()}}
            print(f"w_dense={w:.1f}  recall {rep['overall']['context_recall']:.3f}  "
                  f"precision {rep['overall']['context_precision']:.3f}  "
                  + "  ".join(f"{c[:5]} {v['context_recall']:.2f}" for c, v in rep["per_category"].items()))
        (RESULTS / "weight_sweep.json").write_text(json.dumps(sweep, indent=2))

    info = index_info(chunks, dense, 0, bm25_s, dense=True)
    info["embedding_s"] = timings.get(f"r3_{R3_SIZE}", 0.0)
    run.run_config("R4_hybrid", lambda s, i: hybrid_scores(bm25_scores(s, i), dense.scores(run.qvec[s][i]), W_DENSE),
                   chunks, dict(info))

    # ---- R5: hybrid + HyDE (dense part uses mean of query and hypothetical-document embedding)
    hyde_vec, hyde_lat, hyde_tok = {}, {}, []
    for s, qs in run.sets.items():
        start = time.time()
        passages = hyde_passages(llm, qs, s)
        gen_s = time.time() - start
        texts = [passages[q["id"]] for q in qs]
        pv, emb_s = embed_cached_queries(llm, texts, f"hyde_{s}")
        hyde_vec[s] = _normalise(run.qvec[s] + pv)
        lat_path = CACHE / f"hyde_{s}_latency.json"
        if gen_s > 1 and not lat_path.is_file():  # first run: real generation time
            lat_path.write_text(json.dumps({"gen_s_total": gen_s, "embed_s_total": emb_s, "n": len(qs)}))
        lat = json.loads(lat_path.read_text()) if lat_path.is_file() else {"gen_s_total": 0, "embed_s_total": 0, "n": len(qs)}
        hyde_lat[s] = [(lat["gen_s_total"] + lat["embed_s_total"]) / lat["n"]] * len(qs)
        if s == "dev":
            from retrieval import HYDE_PROMPT
            hyde_tok = [n_tokens(HYDE_PROMPT.format(question=q["question"])) + n_tokens(passages[q["id"]]) for q in qs]
    info = dict(info)
    info["hyde_tokens"] = float(np.mean([n_tokens(t) for t in hyde_passages(llm, run.sets["dev"], "dev").values()]))
    run.run_config("R5_hybrid_hyde",
                   lambda s, i: hybrid_scores(bm25_scores(s, i), dense.scores(hyde_vec[s][i]), W_DENSE),
                   chunks, info, extra_query_tokens=hyde_tok, extra_latency=hyde_lat)

    write_summary(run)
    print(f"\n{llm.usage_summary()}")


def embed_cached_queries(llm, texts, tag):
    path = CACHE / f"{tag}.npy"
    if path.is_file():
        return np.load(path).astype(np.float32), 0.0
    start = time.time()
    v = embed_verified(llm, texts)
    np.save(path, v)
    return v, time.time() - start


def write_summary(run: Runner) -> None:
    cats = ["identifier", "paraphrase", "multi-hop", "version"]
    order = ["R1_bm25", "R2_fixed128", *[f"R3_rec{s}" for s in R3_SIZES], "R4_hybrid", "R5_hybrid_hyde"]
    order = [c for c in order if c in run.metrics]
    lines = ["# Retrieval results (dev, k=5)", "",
             "## Context recall@5 per category", "",
             "| config | " + " | ".join(cats) + " | overall recall | overall precision |",
             "|---|" + "---|" * (len(cats) + 2)]
    for cfg in order:
        m = run.metrics[cfg]
        lines.append(f"| {cfg} | " + " | ".join(f"{m['per_category'][c]['context_recall']:.3f}" for c in cats)
                     + f" | **{m['overall']['context_recall']:.3f}** | {m['overall']['context_precision']:.3f} |")
    lines += ["", "## Context precision@5 per category", "",
              "| config | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
    for cfg in order:
        m = run.metrics[cfg]
        lines.append(f"| {cfg} | " + " | ".join(f"{m['per_category'][c]['context_precision']:.3f}" for c in cats) + " |")
    lines += ["", "## Cost and latency", "",
              "| config | chunks | avg chunk tokens | indexing: embedding s (first run) | BM25 build s | "
              "latency ms median / p95 | LLM tokens per query (retrieval) | context tokens (top-5 chunks) |",
              "|---|---|---|---|---|---|---|---|"]
    for cfg in order:
        s = run.stats[cfg]
        lines.append(f"| {cfg} | {s['n_chunks']} | {s['avg_chunk_tokens']:.0f} | {s['embedding_s']} | {s['bm25_build_s']} | "
                     f"{s['latency_ms_median']} / {s['latency_ms_p95']} | {s['retrieval_llm_tokens_per_query']:.0f} | "
                     f"{s['context_tokens_top5']:.0f} |")
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "summary.json").write_text(json.dumps({"metrics": run.metrics, "stats": run.stats}, indent=2))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
