"""Download the optional ~398 MB Qwen2.5-0.5B Instruct Q4 GGUF from Hugging Face."""
from __future__ import annotations

from pathlib import Path

from .local_llm import LocalPolicyWriter

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit("Install the optional model client first: python -m pip install -r requirements-llm.txt") from exc
    target = ROOT / "models"
    target.mkdir(exist_ok=True)
    path = hf_hub_download(
        repo_id=LocalPolicyWriter.MODEL_REPOSITORY,
        filename=LocalPolicyWriter.MODEL_FILENAME,
        local_dir=str(target),
    )
    print(f"Model downloaded to: {path}")
    print("Set AJCARES_LLM_MODEL_PATH to this file to enable local policy response generation.")


if __name__ == "__main__":
    main()
