"""Read-only clinic information specialist; has no access to scheduling tools."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .rag import PolicyRAG


class ClinicInformationAgent:
    def __init__(self, rag: PolicyRAG | None = None):
        self.rag = rag or PolicyRAG()
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "clinic_catalog.json"
        self.catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    @staticmethod
    def is_directory_question(question: str) -> bool:
        text = question.lower()
        return bool(
            re.search(r"\b(how many|number of|count of|total number)\b.*\b(doctors?|providers?|specialt(?:y|ies)|departments?)\b", text)
            or re.search(r"\b(list|names?|who are|which)\b.*\b(doctors?|providers?)\b", text)
        )

    def reply(self, question: str) -> str:
        if self.is_directory_question(question):
            doctors = self.catalog["doctors"]
            specialties = self.catalog["specialties"]
            text = question.lower()
            if "specialt" in text or "department" in text:
                return f"Our demo clinic directory lists {len(specialties)} specialties: {', '.join(item['name'] for item in specialties)}. [Source: Clinic directory]."
            if any(term in text for term in ("list", "names", "who are", "which")):
                return f"The demo clinic directory lists {len(doctors)} doctors: {', '.join(item['name'] for item in doctors)}. [Source: Clinic directory]."
            return f"The demo clinic directory lists {len(doctors)} doctors across {len(specialties)} specialties. [Source: Clinic directory]."
        return self.rag.answer(question)
