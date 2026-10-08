"""Narrow scheduling tools backed by SQLite; all appointment writes pass here."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import ClinicDatabase, SlotUnavailableError, UnknownPatientError

ROOT = Path(__file__).resolve().parents[1]


class ClinicTools:
    def __init__(self, data_dir: Path | None = None, db_path: str | Path | None = None):
        seed_dir = data_dir or ROOT / "data"
        self.db = ClinicDatabase(db_path or ClinicDatabase.default_path(), seed_dir=seed_dir)
        self.events: list[dict[str, Any]] = []
        self.selection_tokens: dict[str, tuple[str, str]] = {}

    @property
    def patients(self) -> list[dict[str, Any]]:
        """Compatibility view used by the evaluator and demo tooling."""
        patients = self.db.list_patients()
        appointments = self.db.list_appointments()
        for patient in patients:
            patient["appointments"] = [
                {k: v for k, v in appt.items() if k not in {"patient_id", "patient_name", "status", "created_at"}}
                for appt in appointments if appt["patient_id"] == patient["patient_id"] and appt["status"] == "booked"
            ]
        return patients

    @property
    def slots(self) -> list[dict[str, Any]]:
        return self.db.list_slots()

    def _event(self, name: str, **fields: Any) -> None:
        self.events.append({"tool": name, **fields})

    def verify_patient(self, name: str, dob: str) -> dict[str, Any] | None:
        patient = self.db.verify_patient(name, dob)
        self._event("verify_patient", success=bool(patient))
        return patient

    def find_availability(self, reason: str, date: str | None = None) -> list[dict[str, Any]]:
        found = self.db.available_slots(reason, date)
        self._event("find_availability", reason=reason, date=date, result_count=len(found))
        return found

    def record_patient_choice(self, patient: dict[str, Any], slot_id: str, patient_message: str) -> str:
        slot = self.db.get_slot(slot_id)
        utterance = patient_message.lower()
        available_ids = {item["slot_id"] for item in self.db.available_slots()}
        if not slot or slot_id not in available_ids or not (
            slot_id.lower() in utterance or slot["time"].lower() in utterance
        ):
            self._event("record_patient_choice", success=False, slot_id=slot_id)
            raise ValueError("The patient must identify one available slot by ID or time")
        token = f"{patient['patient_id']}:{slot_id}:{len(self.events)}"
        self.selection_tokens[token] = (patient["patient_id"], slot_id)
        self._event("record_patient_choice", success=True, slot_id=slot_id)
        return token

    def book_appointment(
        self,
        patient: dict[str, Any],
        slot_id: str,
        selection_token: str | None,
        confirmation_text: str,
    ) -> dict[str, Any]:
        if not selection_token or self.selection_tokens.get(selection_token) != (patient["patient_id"], slot_id):
            self._event("book_appointment", success=False, reason="missing_specific_choice")
            raise ValueError("A patient-selected slot is required")
        if confirmation_text.strip().lower() not in {"yes", "yeah", "sure", "ok", "okay", "confirm", "i confirm"}:
            self._event("book_appointment", success=False, reason="missing_confirmation")
            raise ValueError("Explicit confirmation is required")
        try:
            appointment = self.db.book_appointment(patient["patient_id"], slot_id)
        except (SlotUnavailableError, UnknownPatientError) as exc:
            self._event("book_appointment", success=False, reason=str(exc))
            raise ValueError(str(exc)) from exc
        self._event("book_appointment", success=True, appointment_id=appointment["appointment_id"], slot_id=slot_id)
        return appointment

    def close(self) -> None:
        self.db.close()
