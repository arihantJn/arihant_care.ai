"""Compare policy retrievers on the small, labeled clinic query set."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .rag import PolicyRAG

ROOT = Path(__file__).resolve().parents[1]


def evaluate(semantic: bool, k: int = 3) -> dict:
    rag = PolicyRAG(semantic=semantic, use_llm=False)
    cases = json.loads((ROOT / "evals" / "retrieval_cases.json").read_text(encoding="utf-8"))
    ranks = []
    rows = []
    abstention_outcomes = []
    for case in cases:
        retrieved = rag.retrieve(case["query"], k=k)
        ids = [item["id"] for item in retrieved]
        expected = case["expected_policy_id"]
        if expected is None:
            correct_abstention = not retrieved
            abstention_outcomes.append(correct_abstention)
            rank = None
        else:
            rank = ids.index(expected) + 1 if expected in ids else None
            ranks.append(rank)
            correct_abstention = None
        rows.append({"query": case["query"], "expected": expected, "retrieved": ids, "rank": rank, "correct_abstention": correct_abstention})
    reciprocal_ranks = [1 / rank if rank else 0 for rank in ranks]
    hits = sum(rank is not None for rank in ranks)
    expected_count = len(ranks)
    return {
        "retriever": "chroma_minilm" if semantic else "keyword_idf",
        "cases": len(cases), "in_scope_cases": expected_count, "k": k, "recall_at_k": round(hits / max(1, expected_count), 3),
        "mrr_at_k": round(sum(reciprocal_ranks) / max(1, len(reciprocal_ranks)), 3),
        "out_of_scope_correct_abstention": round(sum(abstention_outcomes) / max(1, len(abstention_outcomes)), 3),
        "results": rows,
    }


def main() -> None:
    if os.getenv("AJCARES_SEMANTIC_RAG", "0") != "1":
        report = evaluate(semantic=False)
        print("Set AJCARES_SEMANTIC_RAG=1 after installing requirements-rag.txt to evaluate vectors.")
    else:
        report = {"baseline": evaluate(semantic=False), "semantic": evaluate(semantic=True)}
    output = ROOT / "artifacts" / "retrieval_report.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
