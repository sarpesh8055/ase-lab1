"""Retrieval building blocks for Task 3: chunkers, BM25, dense index, hybrid search, HyDE.

Configurations (see configs.py / run_retrieval.py):
    R1  BM25 on the recursive chunks of R3
    R2  fixed-size chunks (token windows with overlap) + dense embeddings
    R3  recursive chunks (headings -> paragraphs -> lines -> sentences) + dense embeddings
    R4  hybrid: min-max normalised BM25 (R1) and cosine (R3), weighted sum
    R5  R4 + HyDE: the dense part searches with the embedding of a hypothetical answer document

Every chunk starts with a metadata header (doc title, type, version), so a chunk out of its
document still says what it is about (important for version questions: "(PaderQueue 2.x)").
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tiktoken
from rank_bm25 import BM25Okapi

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CACHE = HERE / ".cache"
ENC = tiktoken.get_encoding("cl100k_base")


def n_tokens(text: str) -> int:
    return len(ENC.encode(text))


def load_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_corpus() -> list[dict]:
    return load_jsonl(DATA / "corpus.jsonl")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str        # header + body, this is what is embedded, indexed and given to the generator


def header(doc: dict) -> str:
    version = f" | version {doc['version']}" if doc.get("version") else ""
    return f"[{doc['type']}] {doc['title']}{version}\n"


# ============================================================================ chunking

def fixed_chunks(docs: list[dict], size: int = 128, overlap: int = 32) -> list[Chunk]:
    """R2: windows of `size` tokens with `overlap` tokens, within each document (no structure awareness)."""
    chunks = []
    step = size - overlap
    for doc in docs:
        tokens = ENC.encode(doc["text"])
        for n, start in enumerate(range(0, max(1, len(tokens) - overlap), step)):
            body = ENC.decode(tokens[start:start + size])
            chunks.append(Chunk(f"{doc['doc_id']}#f{n}", doc["doc_id"], header(doc) + body))
    return chunks


# separators from coarse to fine: headings, blank lines, single lines (list items / table rows), sentences
SEPARATORS = [r"\n(?=#{1,6} )", r"\n\s*\n", r"\n", r"(?<=[.!?])\s+"]


def _recursive_split(text: str, size: int, level: int = 0) -> list[str]:
    if n_tokens(text) <= size or level >= len(SEPARATORS):
        if n_tokens(text) <= size:
            return [text]
        # last resort: hard split by tokens
        toks = ENC.encode(text)
        return [ENC.decode(toks[i:i + size]) for i in range(0, len(toks), size)]
    pieces = [p for p in re.split(SEPARATORS[level], text) if p.strip()]
    out: list[str] = []
    for piece in pieces:
        out.extend(_recursive_split(piece, size, level + 1) if n_tokens(piece) > size else [piece])
    return out


def _merge(pieces: list[str], size: int, joiner: str = "\n") -> list[str]:
    """Greedily merge neighbouring small pieces up to `size` tokens."""
    merged, current = [], ""
    for p in pieces:
        p = p.strip("\n")
        candidate = f"{current}{joiner}{p}" if current else p
        if current and n_tokens(candidate) > size:
            merged.append(current)
            current = p
        else:
            current = candidate
    if current:
        merged.append(current)
    return merged


def recursive_chunks(docs: list[dict], size: int = 256) -> list[Chunk]:
    """R3: split at the coarsest structural boundary that makes pieces fit, then merge small neighbours.

    The section heading a piece came from is repeated at the start of every chunk of that section,
    so a list item of the changelog still says "## Changed defaults". No token overlap (same for all sizes).
    """
    chunks = []
    for doc in docs:
        h = header(doc)
        budget = max(32, size - n_tokens(h))
        text = doc["text"].strip()
        if n_tokens(text) <= budget:            # whole document fits: one chunk
            bodies = [text]
        else:                                   # split into sections, split big sections further
            pieces = []
            for sec in (s.strip() for s in re.split(SEPARATORS[0], text) if s.strip()):
                if n_tokens(sec) <= budget:
                    pieces.append(sec)
                    continue
                first = sec.splitlines()[0]
                heading = first if first.startswith("#") else ""
                for body in _merge(_recursive_split(sec, budget, 1), budget):
                    if heading and not body.startswith(heading):
                        body = f"{heading} (cont.)\n{body}"
                    pieces.append(body)
            bodies = _merge(pieces, budget, joiner="\n\n")  # neighbouring small sections share a chunk
        for n, body in enumerate(bodies):
            chunks.append(Chunk(f"{doc['doc_id']}#r{n}", doc["doc_id"], h + body))
    return chunks


# ============================================================================ BM25

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[._\-/][a-z0-9]+)*")
STOPWORDS = set("""a an and are as at be by can do does for from how i in is it its my of on or our that the
this to was what when which who why will with you your""".split())


def bm25_tokenize(text: str) -> list[str]:
    """Identifier-aware: `spool.buffer_bytes` -> spool.buffer_bytes, spool, buffer_bytes, buffer, bytes;
    `PQ-E4663` -> pq-e4663, pq, e4663. The whole identifier gives exact matches a high weight,
    the parts still match questions that only mention a component."""
    tokens = []
    for tok in TOKEN_RE.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
        if re.search(r"[._\-/]", tok):
            parts = re.split(r"[.\-/]", tok)
            tokens.extend(p for p in parts if p and p not in STOPWORDS)
            tokens.extend(s for p in parts if "_" in p for s in p.split("_") if s and s not in STOPWORDS)
    return tokens


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([bm25_tokenize(c.text) for c in chunks])

    def scores(self, query: str) -> np.ndarray:
        return np.asarray(self.bm25.get_scores(bm25_tokenize(query)), dtype=np.float32)


# ============================================================================ dense

def _normalise(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


EMBED_BATCH = 32
# Gateway bug we found: the response cache works per text. If a batch contains some texts that are cached
# and some that are not, the vectors come back in the WRONG ORDER (vector i belongs to another text).
# Fix: disable the gateway cache for embedding requests, and verify a random sample against single calls.
NO_CACHE = {"cache": {"no-cache": True}}


def embed_nocache(llm, texts: list[str], batch_size: int = EMBED_BATCH) -> np.ndarray:
    vectors = []
    start = time.time()
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response, meta = llm._with_retries(lambda: llm._create(
            llm._client.embeddings, model=llm.embedding_model, input=batch, extra_body=NO_CACHE))
        llm._count(meta)
        vectors.extend(d.embedding for d in sorted(response.data, key=lambda d: d.index))
    llm._log({"type": "embedding", "model": llm.embedding_model, "n_texts": len(texts), "no_cache": True,
              "duration_s": round(time.time() - start, 3)})
    return _normalise(np.asarray(vectors, dtype=np.float32))


def embed_verified(llm, texts: list[str], n_probe: int = 5) -> np.ndarray:
    """Batch-embed, then re-embed a few random texts one by one and check they match their batch vector."""
    vectors = embed_nocache(llm, texts)
    rng = np.random.default_rng(0)
    probe = rng.choice(len(texts), size=min(n_probe, len(texts)), replace=False)
    single = embed_nocache(llm, [texts[i] for i in probe], batch_size=1)
    sims = np.sum(vectors[probe] * single, axis=1)
    if sims.min() < 0.999:
        raise RuntimeError(f"embedding order check failed (similarities {np.round(sims, 3)}); use a smaller batch size")
    return vectors


def embed_cached(llm, texts: list[str], tag: str) -> tuple[np.ndarray, float]:
    """Embed texts with the gateway model, cached on disk as float16. Returns (vectors, seconds spent embedding)."""
    key = hashlib.sha256((llm.embedding_model + "\x00" + "\x00".join(texts)).encode()).hexdigest()[:16]
    path = CACHE / f"{tag}_{key}.npy"
    if path.is_file():
        return np.load(path).astype(np.float32), 0.0
    start = time.time()
    vectors = embed_verified(llm, texts)
    seconds = time.time() - start
    CACHE.mkdir(exist_ok=True)
    np.save(path, vectors.astype(np.float16))
    return vectors, seconds


class DenseIndex:
    def __init__(self, llm, chunks: list[Chunk], tag: str):
        self.chunks = chunks
        self.vectors, self.embed_seconds = embed_cached(llm, [c.text for c in chunks], tag)

    def scores(self, query_vector: np.ndarray) -> np.ndarray:
        return self.vectors @ query_vector


# ============================================================================ ranking helpers

def minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    return np.zeros_like(x) if hi - lo < 1e-12 else (x - lo) / (hi - lo)


def hybrid_scores(bm25: np.ndarray, dense: np.ndarray, w_dense: float) -> np.ndarray:
    """Both score lists are min-max normalised to [0, 1] per query, then combined.
    (BM25 is unbounded, cosine is in [-1, 1] and in practice squeezed into ~[0.3, 0.8].)"""
    return w_dense * minmax(dense) + (1 - w_dense) * minmax(bm25)


def top_chunks(scores: np.ndarray, chunks: list[Chunk], n: int) -> list[tuple[Chunk, float]]:
    order = np.argsort(-scores)[:n]
    return [(chunks[i], float(scores[i])) for i in order]


def to_doc_ids(ranked: list[tuple[Chunk, float]]) -> list[str]:
    seen, out = set(), []
    for c, _ in ranked:
        if c.doc_id not in seen:
            seen.add(c.doc_id)
            out.append(c.doc_id)
    return out


def top_k_doc_chunks(ranked: list[tuple[Chunk, float]], k: int) -> list[Chunk]:
    """The best chunk of each of the top-k documents (what we give to the generator)."""
    seen, out = set(), []
    for c, _ in ranked:
        if c.doc_id not in seen:
            seen.add(c.doc_id)
            out.append(c)
            if len(out) == k:
                break
    return out


# ============================================================================ HyDE

HYDE_PROMPT = """You help search the documentation of PaderQueue, a message queue.
Write a short passage (3-5 sentences) that could appear in its documentation and answers the question below.
Use the style of technical reference documentation: name likely configuration options (e.g. `component.option`),
error codes, CLI commands or components where it fits. It is fine to guess details.

Question: {question}

Passage:"""


def hyde_passages(llm, questions: list[dict], tag: str) -> dict[str, str]:
    """Generates (and caches) one hypothetical document per question."""
    path = CACHE / f"hyde_{tag}.json"
    from concurrent.futures import ThreadPoolExecutor

    cache = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    todo = [q for q in questions if q["id"] not in cache]

    def gen(q):
        return q["id"], llm.chat([{"role": "user", "content": HYDE_PROMPT.format(question=q["question"])}]).strip()

    with ThreadPoolExecutor(max_workers=4) as pool:  # gateway limit: max 10 parallel requests per key
        for qid, text in pool.map(gen, todo):
            cache[qid] = text
    if todo:
        CACHE.mkdir(exist_ok=True)
        path.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return cache
