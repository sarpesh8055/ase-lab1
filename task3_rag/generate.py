"""Generates answers from retrieved chunks (end-to-end evaluation and test predictions).

    uv run python task3_rag/generate.py --config R4_hybrid --set dev --sample 50
    uv run python task3_rag/generate.py --config R5_hybrid_hyde --set test        # -> predictions_test.jsonl

Reads results/retrieval_<config>_<set>.jsonl (written by run_retrieval.py), takes the best chunk of each of
the top-5 documents as context, and asks the chat model to answer from that context only.
Output: results/answers_<config>_<set>.jsonl  ({"id", "answer", "contexts", "retrieved_doc_ids"}),
for --set test additionally task3_rag/predictions_test.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common.llm_client import LLMClient  # noqa: E402
from judge import ABSTENTION, stratified_sample  # noqa: E402
from retrieval import header, fixed_chunks, load_corpus, load_jsonl, n_tokens, recursive_chunks  # noqa: E402
from run_retrieval import R2_OVERLAP, R2_SIZE, R3_SIZE  # noqa: E402

RESULTS = HERE / "results"
K = 5

PROMPT = """You answer questions about PaderQueue, a message queue, using ONLY the documentation excerpts below.

Rules:
- Use only facts from the excerpts. Do not use outside knowledge.
- If the excerpts do not contain the answer, reply exactly: {abstention}
- Mind versions: if the question asks about a specific version (e.g. 2.x), use the page for that version;
  otherwise the current version (4.x) applies. Release notes list changed defaults.
- Official reference pages (config, error, cli, runbook, changelog) win over forum posts. Forum answers can be wrong
  or outdated; incident reports describe what happened, not the recommended fix.
- For questions that combine two facts (e.g. "the error that caused incident X"), first find the first fact,
  then answer with the second. If the second part is missing from the excerpts, say what you found and what is missing.
- Answer in 1-3 sentences. Name the exact option, error code, value or command.

DOCUMENTATION EXCERPTS:
{context}

QUESTION: {question}

ANSWER:"""


def chunks_for(config: str):
    docs = load_corpus()
    if config.startswith("R2"):
        return fixed_chunks(docs, size=R2_SIZE, overlap=R2_OVERLAP)
    if config.startswith("R3_rec"):
        return recursive_chunks(docs, size=int(config.removeprefix("R3_rec")))
    return recursive_chunks(docs, size=R3_SIZE)  # R1, R4, R5


def context_chunks(chunk_ids: list[str], by_id: dict) -> list:
    seen, out = set(), []
    for cid in chunk_ids:
        c = by_id[cid]
        if c.doc_id not in seen:
            seen.add(c.doc_id)
            out.append(c)
            if len(out) == K:
                break
    return out


DOC_CONTEXT_MAX_TOKENS = 400


def doc_contexts(chunk_ids: list[str], by_id: dict, docs: dict) -> list[str]:
    """Small-to-big: rank with chunks, but give the generator the WHOLE document for each of the top-k documents
    (header + full text) if it has at most DOC_CONTEXT_MAX_TOKENS tokens. Longer documents (changelogs) contribute
    their retrieved chunks of that document, in rank order, up to the same budget."""
    order, per_doc = [], {}
    for cid in chunk_ids:
        c = by_id[cid]
        if c.doc_id not in per_doc:
            if len(order) == K:
                continue
            order.append(c.doc_id)
            per_doc[c.doc_id] = []
        per_doc[c.doc_id].append(c)
    out = []
    for doc_id in order:
        doc = docs[doc_id]
        full = header(doc) + doc["text"]
        if n_tokens(full) <= DOC_CONTEXT_MAX_TOKENS:
            out.append(full)
            continue
        parts, used = [], 0
        for c in per_doc[doc_id]:
            t = n_tokens(c.text)
            if parts and used + t > DOC_CONTEXT_MAX_TOKENS:
                break
            parts.append(c.text)
            used += t
        out.append("\n[...]\n".join(parts))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--set", choices=["dev", "test"], default="dev")
    parser.add_argument("--sample", type=int, help="dev only: the same stratified sample judge.py uses")
    parser.add_argument("--model", default=None)
    parser.add_argument("--context", choices=["doc", "chunk"], default="doc",
                        help="doc: whole documents of the top-5 (default); chunk: best chunk per document (v1)")
    args = parser.parse_args()

    questions = load_jsonl(HERE / "data" / f"questions_{args.set}.jsonl")
    if args.sample:
        questions = stratified_sample(questions, args.sample)
    retrieved = {r["id"]: r for r in load_jsonl(RESULTS / f"retrieval_{args.config}_{args.set}.jsonl")}
    by_id = {c.chunk_id: c for c in chunks_for(args.config)}
    docs = {d["doc_id"]: d for d in load_corpus()}

    llm = LLMClient(model=args.model, log_path=HERE / "logs" / f"generate_{args.config}_{args.set}.jsonl")

    def answer(q):
        ids = retrieved[q["id"]]["retrieved_chunk_ids"]
        top = context_chunks(ids, by_id)
        ctx = doc_contexts(ids, by_id, docs) if args.context == "doc" else [c.text for c in top]
        context = "\n\n---\n\n".join(f"[{i + 1}] {t}" for i, t in enumerate(ctx))
        prompt = PROMPT.format(abstention=ABSTENTION, context=context, question=q["question"])
        start = time.time()
        text = llm.chat([{"role": "user", "content": prompt}]).strip()
        return {"id": q["id"], "answer": text, "contexts": ctx,
                "retrieved_doc_ids": [c.doc_id for c in top],
                "latency_s": round(time.time() - start, 2), "prompt_tokens_est": n_tokens(prompt)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(answer, questions))

    suffix = ("_s" + str(args.sample) if args.sample else "") + ("_chunkctx" if args.context == "chunk" else "")
    out = RESULTS / f"answers_{args.config}_{args.set}{suffix}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(rows)} answers)")
    if args.set == "test":
        pred = HERE / "predictions_test.jsonl"
        with pred.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"id": r["id"], "answer": r["answer"],
                                    "retrieved_doc_ids": r["retrieved_doc_ids"]}, ensure_ascii=False) + "\n")
        print(f"wrote {pred}")
    lat = sorted(r["latency_s"] for r in rows)
    print(f"generation latency median {lat[len(lat) // 2]} s, prompt tokens mean "
          f"{sum(r['prompt_tokens_est'] for r in rows) / len(rows):.0f}; {llm.usage_summary()}")


if __name__ == "__main__":
    main()
