"""Failure analysis + material for the manual judge check.

    uv run python task3_rag/analyze.py R5_hybrid_hyde

For every judged question that is not fully correct: was the needed information in the contexts
(retrieval failure vs generation failure)? Writes results/failures_<cfg>.md and results/judge_check_<cfg>.md
(10 judge decisions, stratified, with question, ground truth, answer and the judge's reason, for checking by hand).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from retrieval import load_corpus, load_jsonl  # noqa: E402

RESULTS = HERE / "results"


def main(cfg: str) -> None:
    qs = {q["id"]: q for q in load_jsonl(HERE / "data" / "questions_dev.jsonl")}
    answers = {a["id"]: a for a in load_jsonl(RESULTS / f"answers_{cfg}_dev_s50.jsonl")}
    judged = load_jsonl(RESULTS / f"judge_{cfg}.jsonl")
    titles = {d["doc_id"]: f"{d['doc_id']} ({d['type']}: {d['title']})" for d in load_corpus()}

    lines = [f"# Failures of {cfg} on the judged dev sample (correctness < 1)", ""]
    counts = {"retrieval": 0, "generation": 0, "partial retrieval": 0}
    for j in judged:
        if j["correctness"] >= 1:
            continue
        q, a = qs[j["id"]], answers[j["id"]]
        groups = q["relevant_doc_ids"]
        got = set(a["retrieved_doc_ids"])
        covered = [bool(got & set(g)) for g in groups]
        if groups and not any(covered):
            kind = "retrieval"
        elif groups and not all(covered):
            kind = "partial retrieval"
        else:
            kind = "generation"
        counts[kind] += 1
        lines += [f"## {j['id']} ({q['category']}) – correctness {j['correctness']} – **{kind} failure**", "",
                  f"- Question: {q['question']}", f"- Ground truth: {q['answer']}", f"- Answer: {a['answer']}",
                  f"- Needed (groups): {[[titles[d] for d in g] for g in groups]}",
                  f"- Retrieved top-5: {[titles[d] for d in a['retrieved_doc_ids']]}",
                  f"- Judge: {j['correctness_reason']}", ""]
    lines.insert(2, f"Counts: {counts}\n")
    (RESULTS / f"failures_{cfg}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:3]))

    # 10 judge decisions for a manual check: 2 per category
    by_cat: dict[str, list] = {}
    for j in judged:
        by_cat.setdefault(j["category"], []).append(j)
    pick = [j for cat in sorted(by_cat) for j in by_cat[cat][:2]]
    out = [f"# Manual check of 10 judge decisions ({cfg})", "",
           "Fill in the last line of every block: agree / disagree + why.", ""]
    for j in pick:
        q, a = qs[j["id"]], answers[j["id"]]
        out += [f"## {j['id']} ({q['category']})", "", f"- Question: {q['question']}",
                f"- Ground truth: {q['answer']}", f"- Answer: {a['answer']}",
                f"- Judge: correctness **{j['correctness']}**, faithfulness {j['faithfulness']}, "
                f"relevance {j['answer_relevance']:.2f} – {j['correctness_reason']}",
                f"- Claims: {json.dumps(j['claims'], ensure_ascii=False)}",
                "- **Our verdict:** ", ""]
    (RESULTS / f"judge_check_{cfg}.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote results/failures_{cfg}.md and results/judge_check_{cfg}.md")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "R5_hybrid_hyde")
