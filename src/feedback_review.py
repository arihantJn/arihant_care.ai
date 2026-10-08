"""Prepare human-reviewed feedback summaries as candidate regression cases."""
from __future__ import annotations

import json
from pathlib import Path

from .database import ClinicDatabase

ROOT = Path(__file__).resolve().parents[1]


def export_candidates() -> list[dict]:
    db = ClinicDatabase()
    candidates = []
    for item in db.list_unreviewed_feedback():
        if item["rating"] < 3:
            candidates.append({
                "feedback_id": item["feedback_id"],
                "reason": item["reason"],
                "review_status": "needs_human_review",
                "candidate_scenario": None,
                "review_instruction": "Sanitize the report, define expected safe behavior, then add it as a regression scenario. Feedback never changes live behavior automatically.",
            })
    output = ROOT / "artifacts" / "feedback_candidates.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
    db.close()
    return candidates


if __name__ == "__main__":
    print(json.dumps(export_candidates(), indent=2))
