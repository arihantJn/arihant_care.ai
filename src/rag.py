"""Tiny deterministic retrieval layer for the clinic's approved policy corpus."""
from __future__ import annotations

import json
import math
import os
import re
import importlib.util
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class PolicyRAG:
    """Policy retrieval with a deterministic keyword fallback.

    Set AJCARES_SEMANTIC_RAG=1 after installing optional RAG dependencies to
    use persistent Chroma vectors. The small embedding model downloads on first use.
    """

    MODEL_NAME = "all-MiniLM-L6-v2 (Chroma default embedding function)"
    COLLECTION_NAME = "clinic_policies_v1"
    # Initial threshold selected against the included toy in/out-of-scope set;
    # it is not a calibrated confidence and must be re-evaluated on held-out data.
    MIN_SIMILARITY = 0.20

    def __init__(self, path: Path | None = None, semantic: bool | None = None, persist_dir: Path | None = None, use_llm: bool = True):
        self.docs = json.loads((path or ROOT / "data" / "clinic_policies.json").read_text(encoding="utf-8"))
        self.term_counts = [Counter(tokens(d["title"] + " " + d["text"])) for d in self.docs]
        self.doc_freq = Counter(t for c in self.term_counts for t in c)
        if semantic is None:
            configured_semantic = os.getenv("AJCARES_SEMANTIC_RAG")
            self.semantic = configured_semantic == "1" if configured_semantic is not None else importlib.util.find_spec("chromadb") is not None
        else:
            self.semantic = semantic
        self.persist_dir = persist_dir or ROOT / "data" / "chroma"
        self.collection: Any = None
        self.embedding_model: Any = None
        self.policy_writer: Any = None
        if self.semantic:
            self._initialize_vector_index()
        default_model_path = ROOT / "models" / "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
        model_path = os.getenv("AJCARES_LLM_MODEL_PATH") or (str(default_model_path) if default_model_path.exists() else None)
        llm_enabled = os.getenv("AJCARES_LLM_ENABLED", "1") != "0"
        if use_llm and model_path and llm_enabled:
            from .local_llm import LocalPolicyWriter
            self.policy_writer = LocalPolicyWriter(model_path)

    def _initialize_vector_index(self) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("Semantic RAG is optional. Install requirements-rag.txt to enable Chroma and embeddings.") from exc

        client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "model": self.MODEL_NAME, "policy_source": "clinic_policies.json"},
        )
        existing = self.collection.get(include=["metadatas"])
        indexed = {item.get("policy_id") for item in (existing.get("metadatas") or [])}
        missing = [doc for doc in self.docs if doc["id"] not in indexed]
        if missing:
            self.collection.add(
                ids=[doc["id"] for doc in missing],
                documents=[f"{doc['title']}\n{doc['text']}" for doc in missing],
                metadatas=[{"policy_id": doc["id"], "title": doc["title"], "source": "clinic_policies.json", "version": "1"} for doc in missing],
            )

    def retrieve(self, query: str, k: int = 2) -> list[dict]:
        if self.collection is not None:
            result = self.collection.query(query_texts=[query], n_results=min(k, self.collection.count()))
            matches = []
            for index, (doc_id, distance) in enumerate(zip(result["ids"][0], result["distances"][0])):
                metadata = result["metadatas"][0][index] or {}
                source = next((doc for doc in self.docs if doc["id"] == doc_id), None)
                if source is None:
                    continue
                matches.append({**source, "score": round(max(0.0, 1.0 - float(distance)), 4), "distance": round(float(distance), 4), "metadata": metadata})
            if matches and matches[0]["score"] < self.MIN_SIMILARITY:
                return []
            return matches
        q = set(tokens(query))
        scored = []
        n = len(self.docs)
        for doc, counts in zip(self.docs, self.term_counts):
            score = sum((1 + math.log(counts[t])) * (math.log(1 + n / (1 + self.doc_freq[t]))) for t in q if t in counts)
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda x: (-x[0], x[1]["id"]))
        return [dict(d, score=round(s, 3)) for s, d in scored[:k]]

    def answer(self, query: str) -> str:
        docs = self.retrieve(query, k=1)
        if not docs:
            return "I don't have an approved clinic policy passage for that. I can connect you with clinic staff."
        if self.policy_writer is not None:
            try:
                return self.policy_writer.answer_from_policy(query, docs)
            except Exception:
                # If local generation fails, retain the citation-backed deterministic answer.
                pass
        return " ".join(f"{d['text']} [Source: {d['title']}]." for d in docs)


@lru_cache(maxsize=1)
def shared_policy_rag() -> PolicyRAG:
    """Reuse the local embedding index and optional generator across chat sessions."""
    return PolicyRAG()
