"""RAG component for Task 2: chunk, embed and search the style guide.

Chunking
    Every style guide document is split at its level-2 headings ("## ..."). The text before the
    first "##" is the intro chunk. Every chunk is prefixed with the document header
    (id, title, status), so that a chunk on its own still says which document it comes from and
    whether that document is ACTIVE or DEPRECATED. That header is embedded too, which helps
    queries like "night mode colors" find the right document.
    Very long sections (> MAX_CHUNK_TOKENS) are split further at paragraph / list-item boundaries.

Embeddings
    Gateway embedding model ($LAB_EMBEDDING_MODEL, free) via LLMClient.embed. Vectors are
    L2-normalised and kept in a numpy matrix; cosine similarity = dot product.
    Vectors are cached on disk (.cache/), keyed by a hash of model + chunk texts, so a
    second run does not re-embed.

Usage
    from rag import StyleGuideIndex
    index = StyleGuideIndex.build(llm)
    chunks = index.search("night mode background color", k=5)

    # command line (from the repository root):
    uv run python task2_own_agent/rag.py "night mode colors"     # show the top chunks
    uv run python task2_own_agent/rag.py --eval                  # retrieval sanity check
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common.llm_client import LLMClient, count_tokens  # noqa: E402

STYLE_GUIDE_DIR = HERE / "style_guide"
CACHE_DIR = HERE / ".cache"
MAX_CHUNK_TOKENS = 300
MAX_OBSERVATION_TOKENS = 1000  # hard limit from the task specification


@dataclass
class Chunk:
    doc_id: str        # e.g. "SG-13"
    title: str         # e.g. "Night mode palette (version 2)"
    status: str        # e.g. "ACTIVE (version 2)" or "DEPRECATED – replaced by SG-13"
    section: str       # heading of the section, "" for the intro
    text: str          # chunk text including the document header
    score: float = 0.0

    @property
    def deprecated(self) -> bool:
        return self.status.upper().startswith("DEPRECATED")


# --------------------------------------------------------------------------- chunking

def _split_long(text: str, max_tokens: int) -> list[str]:
    """Split a section body at blank lines / list items until every part fits."""
    if count_tokens(text) <= max_tokens:
        return [text]
    blocks = re.split(r"\n(?=\s*\n)|\n(?=- |\d+\. )", text)
    parts, current = [], ""
    for block in blocks:
        candidate = (current + "\n" + block).strip() if current else block.strip()
        if current and count_tokens(candidate) > max_tokens:
            parts.append(current)
            current = block.strip()
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_document(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()
    m = re.match(r"#\s*(SG-\d+)\s*:\s*(.+)", lines[0])
    doc_id, title = (m.group(1), m.group(2).strip()) if m else (path.stem.split("_")[0], lines[0].lstrip("# "))
    status = next((l.split(":", 1)[1].strip() for l in lines[1:6] if l.lower().startswith("status:")), "UNKNOWN")
    category = next((l.split(":", 1)[1].strip() for l in lines[1:6] if l.lower().startswith("category:")), "")

    body_lines = [l for l in lines[1:] if not re.match(r"(status|category)\s*:", l, re.I)]
    body = "\n".join(body_lines).strip()
    header = f"[{doc_id}] {title}\nStatus: {status}" + (f" | Category: {category}" if category else "")

    # split at "## " headings, keep the heading with its section
    sections = re.split(r"\n(?=##\s)", "\n" + body)
    chunks = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        heading = sec.splitlines()[0].lstrip("# ").strip() if sec.startswith("##") else ""
        for part in _split_long(sec, MAX_CHUNK_TOKENS):
            chunks.append(Chunk(doc_id, title, status, heading, f"{header}\n\n{part}"))
    return chunks


def load_chunks(style_dir: Path = STYLE_GUIDE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(style_dir.glob("*.md")):
        chunks.extend(chunk_document(path))
    return chunks


# --------------------------------------------------------------------------- index

class StyleGuideIndex:
    def __init__(self, llm: LLMClient, chunks: list[Chunk], vectors: np.ndarray):
        self.llm = llm
        self.chunks = chunks
        self.vectors = vectors  # (n, dim), L2-normalised

    @classmethod
    def build(cls, llm: LLMClient, style_dir: Path = STYLE_GUIDE_DIR, use_cache: bool = True) -> "StyleGuideIndex":
        chunks = load_chunks(style_dir)
        texts = [c.text for c in chunks]
        key = hashlib.sha256((str(llm.embedding_model) + "\x00" + "\x00".join(texts)).encode()).hexdigest()[:16]
        cache_file = CACHE_DIR / f"embeddings_{key}.npy"
        if use_cache and cache_file.is_file():
            vectors = np.load(cache_file)
        else:
            vectors = _normalise(llm.embed(texts, batch_size=16))  # larger batches come back mis-ordered from the gateway
            if use_cache:
                CACHE_DIR.mkdir(exist_ok=True)
                np.save(cache_file, vectors)
        return cls(llm, chunks, vectors)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        """Top-k chunks by cosine similarity, each with its source document id."""
        q = _normalise(self.llm.embed([query]))[0]
        scores = self.vectors @ q
        order = np.argsort(-scores)[:k]
        result = []
        for i in order:
            c = self.chunks[i]
            result.append(Chunk(c.doc_id, c.title, c.status, c.section, c.text, float(scores[i])))
        return result


def _normalise(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(norms, 1e-12)


def format_observation(query: str, chunks: list[Chunk], max_tokens: int = MAX_OBSERVATION_TOKENS) -> tuple[str, list[str]]:
    """Render chunks for the model, staying within `max_tokens` of style guide text.

    Returns (observation text, list of doc ids that were included). Chunks are added in rank
    order until the budget is used up; a chunk that does not fit is skipped (we never cut a
    rule in half, except when even the first chunk alone is too long).
    """
    parts, used, ids = [], 0, []
    for c in chunks:
        block = c.text + ("\n(!) This document is DEPRECATED. Follow the document that replaces it."
                          if c.deprecated else "")
        t = count_tokens(block)
        if used + t > max_tokens:
            if not parts:  # first chunk alone too long: truncate it
                while block and count_tokens(block) > max_tokens:
                    block = block[: int(len(block) * 0.9)]
                parts.append(block + " [...]")
                ids.append(c.doc_id)
            continue
        parts.append(block)
        used += t
        ids.append(c.doc_id)
    text = f'Style guide results for "{query}" ({len(parts)} chunks):\n\n' + "\n\n---\n\n".join(parts)
    return text, ids


def style_guide_tokens(observation: str) -> int:
    """Tokens of style guide text in an observation (everything after the first line)."""
    return count_tokens(observation.split("\n", 2)[-1])


# --------------------------------------------------------------------------- CLI / sanity check

# Hand-written queries with the ACTIVE document that must be retrieved.
EVAL_QUERIES = [
    ("night mode background and text colors", "SG-13"),
    ("day mode palette colors", "SG-11"),
    ("accent color variable", "SG-14"),
    ("how to switch between light and dark theme in CSS and JavaScript", "SG-20"),
    ("remember the chosen theme across page reloads", "SG-21"),
    ("theme toggle button requirements", "SG-22"),
    ("member card markup", "SG-30"),
    ("hot take badge", "SG-31"),
    ("footer text", "SG-40"),
    ("mobile breakpoint width", "SG-50"),
    ("which font family to use", "SG-51"),
    ("font size units", "SG-52"),
    ("page title format", "SG-02"),
    ("required sections and their ids", "SG-35"),
    ("how many h1 headings", "SG-36"),
    ("animations and reduced motion", "SG-55"),
    ("alt text for member photos", "SG-33"),
    ("future of software engineering section", "SG-37"),
]


def run_eval(index: StyleGuideIndex, k: int) -> None:
    hits = 0
    for query, expected in EVAL_QUERIES:
        ids = [c.doc_id for c in index.search(query, k)]
        ok = expected in ids
        hits += ok
        rank = ids.index(expected) + 1 if ok else "-"
        print(f"[{'HIT ' if ok else 'MISS'}] rank {rank!s:>2}  {expected}  {query!r}  -> {ids}")
    print(f"\nhit@{k}: {hits}/{len(EVAL_QUERIES)} = {hits / len(EVAL_QUERIES):.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the style guide.")
    parser.add_argument("query", nargs="?")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--eval", action="store_true", help="run the retrieval sanity check")
    args = parser.parse_args()

    llm = LLMClient(log_path=HERE / "logs" / "rag_cli.jsonl")
    index = StyleGuideIndex.build(llm)
    print(f"{len(index.chunks)} chunks from {len({c.doc_id for c in index.chunks})} documents, "
          f"dim {index.vectors.shape[1]}\n")
    if args.eval:
        run_eval(index, args.k)
    elif args.query:
        text, _ = format_observation(args.query, index.search(args.query, args.k))
        print(text)
        print(f"\n[{style_guide_tokens(text)} tokens of style guide text]")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
