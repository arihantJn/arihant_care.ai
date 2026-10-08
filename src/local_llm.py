"""Optional, local-only policy wording model. Scheduling decisions stay in code."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class LocalPolicyWriter:
    MODEL_REPOSITORY = "bartowski/Qwen2.5-0.5B-Instruct-GGUF"
    MODEL_FILENAME = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
    APPROX_DOWNLOAD = "398 MB"

    def __init__(self, model_path: str | Path | None = None):
        selected_path = model_path or os.getenv("AJCARES_LLM_MODEL_PATH")
        if not selected_path:
            raise RuntimeError("Local LLM is disabled. Set AJCARES_LLM_MODEL_PATH to the downloaded GGUF file.")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError("Install requirements-llm.txt to use the optional local response model.") from exc
        self.model: Any = Llama(
            model_path=str(selected_path), n_ctx=2048, n_threads=max(2, min(6, os.cpu_count() or 2)),
            n_gpu_layers=0, verbose=False,
        )

    def answer_from_policy(self, question: str, passages: list[dict]) -> str:
        reference = passages[0]
        result = self.model.create_chat_completion(
            messages=[
                {"role": "system", "content": (
                    "Answer as a clinic information assistant. Use only facts stated in the reference. "
                    "Write one direct sentence of at most 15 words. Do not repeat yourself, list alternatives, "
                    "or mention facts the patient did not ask about. Never give medical advice or claim an action was done."
                )},
                {"role": "user", "content": f"Reference: {reference['text']}\nQuestion: {question}\nGive one direct answer."},
            ],
            max_tokens=48,
            temperature=0.0,
            top_p=0.8,
        )
        answer = str(result["choices"][0]["message"]["content"]).strip()
        answer = answer.splitlines()[0].strip()
        answer = answer.split(". ", 1)[0].strip()
        if not answer:
            raise RuntimeError("The local model returned an empty answer")
        if len(answer.split()) > 25 or len(answer) > 240:
            raise RuntimeError("The local model exceeded the concise answer limit")
        sources = ", ".join(item["title"] for item in passages)
        return f"{answer} [Source: {sources}]."
