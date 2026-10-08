"""Bounded reminder worker: preview only; it never sends messages externally."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .database import ClinicDatabase


class ReminderAgent:
    """Time-triggered reminder specialist with read-only booking access.

    It reads opted-in appointments and records a local, masked preview. Actual
    email/SMS delivery is intentionally a separate future integration.
    """

    def __init__(self, db: ClinicDatabase | None = None):
        self.db = db or ClinicDatabase()

    def preview(self, days_ahead: int = 2, today: date | None = None) -> list[dict[str, Any]]:
        if not 0 <= days_ahead <= 30:
            raise ValueError("days_ahead must be between 0 and 30")
        start = today or date.today()
        end = start + timedelta(days=days_ahead)
        appointments = self.db.upcoming_opted_in_appointments(start.isoformat(), end.isoformat())
        previews = []
        for item in appointments:
            created = self.db.record_reminder_preview(
                item["appointment_id"], item["preferred_channel"], item["contact"]
            )
            if not created:
                continue
            previews.append({
                "appointment_id": item["appointment_id"], "patient_id": item["patient_id"],
                "patient_name": item["name"], "date": item["date"], "time": item["time"],
                "channel": item["preferred_channel"], "delivery": "preview_only",
                "message": f"Reminder preview: {item['name']}, your {item['reason']} appointment is {item['date']} at {item['time']} with {item['provider']}.",
            })
        return previews
