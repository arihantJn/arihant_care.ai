"""SQLite persistence for demo patients, appointment slots, and bookings."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "clinic.db"


class DuplicatePatientError(ValueError):
    pass


class UnknownPatientError(LookupError):
    pass


class SlotUnavailableError(ValueError):
    pass


class ClinicDatabase:
    """Small SQLite repository; one instance is shared by a CLI/API process."""

    def __init__(self, path: str | Path = DEFAULT_DB, seed_dir: Path | None = None):
        self.path = str(path)
        self._lock = threading.RLock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._initialize()
        if seed_dir is not None:
            self._seed(seed_dir)

    @staticmethod
    def default_path() -> Path:
        return DEFAULT_DB

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            dob TEXT NOT NULL,
            contact TEXT,
            preferred_channel TEXT NOT NULL DEFAULT 'none'
                CHECK (preferred_channel IN ('none', 'email', 'sms')),
            preferred_language TEXT NOT NULL DEFAULT 'en',
            reminder_consent INTEGER NOT NULL DEFAULT 0 CHECK (reminder_consent IN (0, 1)),
            created_at TEXT NOT NULL,
            UNIQUE (name COLLATE NOCASE, dob)
        );
        CREATE TABLE IF NOT EXISTS slots (
            slot_id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            reason TEXT NOT NULL CHECK (reason IN ('checkup', 'follow-up')),
            provider TEXT NOT NULL,
            specialty_id TEXT NOT NULL DEFAULT 'family-medicine',
            specialty TEXT NOT NULL DEFAULT 'Family Medicine',
            doctor_id TEXT NOT NULL DEFAULT '',
            clinic TEXT NOT NULL DEFAULT 'Main Clinic'
        );
        CREATE TABLE IF NOT EXISTS appointments (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id TEXT NOT NULL UNIQUE,
            patient_id TEXT NOT NULL REFERENCES patients(patient_id),
            slot_id TEXT NOT NULL REFERENCES slots(slot_id),
            status TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked', 'cancelled')),
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_slot
            ON appointments(slot_id) WHERE status = 'booked';
        CREATE INDEX IF NOT EXISTS appointments_by_patient
            ON appointments(patient_id, status);
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL DEFAULT '',
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            reason TEXT NOT NULL,
            comment TEXT,
            reviewed INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminder_runs (
            reminder_id TEXT PRIMARY KEY,
            appointment_id TEXT NOT NULL REFERENCES appointments(appointment_id),
            channel TEXT NOT NULL,
            recipient_masked TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('preview', 'sent')),
            created_at TEXT NOT NULL,
            UNIQUE (appointment_id, status)
        );
        """
        with self._lock:
            self._conn.executescript(schema)
            feedback_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(feedback)").fetchall()}
            if "turn_id" not in feedback_columns:
                self._conn.execute("ALTER TABLE feedback ADD COLUMN turn_id TEXT NOT NULL DEFAULT ''")
            slot_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(slots)").fetchall()}
            for column, definition in {
                "specialty_id": "TEXT NOT NULL DEFAULT 'family-medicine'",
                "specialty": "TEXT NOT NULL DEFAULT 'Family Medicine'",
                "doctor_id": "TEXT NOT NULL DEFAULT ''",
                "clinic": "TEXT NOT NULL DEFAULT 'Main Clinic'",
            }.items():
                if column not in slot_columns:
                    self._conn.execute(f"ALTER TABLE slots ADD COLUMN {column} {definition}")
            self._conn.execute("UPDATE appointments SET status = 'cancelled' WHERE status = 'booked' AND appointment_id LIKE 'DEMO-%'")
            old_relative_slots = self._conn.execute("SELECT slot_id, date FROM slots WHERE date LIKE 'Day %'").fetchall()
            for row in old_relative_slots:
                try:
                    offset = int(row["date"].split()[1]) - 1
                    real_date = (date.today() + timedelta(days=offset)).isoformat()
                    self._conn.execute("UPDATE slots SET date = ? WHERE slot_id = ?", (real_date, row["slot_id"]))
                except (ValueError, IndexError):
                    continue

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _seed(self, seed_dir: Path) -> None:
        patient_file = seed_dir / "appointments.json"
        slot_file = seed_dir / "slots.json"
        patients = json.loads(patient_file.read_text(encoding="utf-8")) if patient_file.exists() else []
        slots = json.loads(slot_file.read_text(encoding="utf-8")) if slot_file.exists() else []
        with self._lock, self._conn:
            for item in patients:
                self._conn.execute(
                    """INSERT OR IGNORE INTO patients
                       (patient_id, name, dob, created_at) VALUES (?, ?, ?, ?)""",
                    (item["patient_id"], item["name"], item["dob"], self._now()),
                )
            today = date.today()
            for item in slots:
                slot_day = item["date"]
                if slot_day.startswith("Day "):
                    try:
                        offset = int(slot_day.split()[1]) - 1
                        slot_day = (today + timedelta(days=offset)).isoformat()
                    except (ValueError, IndexError):
                        pass
                self._conn.execute(
                    """INSERT OR IGNORE INTO slots
                       (slot_id, date, time, reason, provider, specialty_id, specialty, doctor_id, clinic)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["slot_id"], slot_day, item["time"], item.get("reason", "checkup"),
                     item["provider"], item.get("specialty_id", "family-medicine"),
                     item.get("specialty", "Family Medicine"), item.get("doctor_id", ""),
                     item.get("clinic", "Main Clinic")),
                )
            for item in patients:
                for appointment in item.get("appointments", []):
                    self._conn.execute(
                        """INSERT OR IGNORE INTO appointments
                           (appointment_id, patient_id, slot_id, status, created_at)
                           VALUES (?, ?, ?, 'booked', ?)""",
                        (appointment["appointment_id"], item["patient_id"], appointment["slot_id"], self._now()),
                    )

    def create_patient(
        self,
        name: str,
        dob: str,
        contact: str | None = None,
        preferred_channel: str = "none",
        preferred_language: str = "en",
        reminder_consent: bool = False,
    ) -> dict[str, Any]:
        patient_id = f"P{secrets.token_hex(5).upper()}"
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO patients
                       (patient_id, name, dob, contact, preferred_channel,
                        preferred_language, reminder_consent, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (patient_id, name.strip(), dob, contact, preferred_channel, preferred_language,
                     int(reminder_consent), self._now()),
                )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "patients.name" in message and "patients.dob" in message:
                raise DuplicatePatientError("A patient with that name and date of birth already exists") from exc
            raise
        return self.get_patient(patient_id)  # type: ignore[return-value]

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
        return dict(row) if row else None

    def verify_patient(self, name: str, dob: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM patients WHERE name = ? COLLATE NOCASE AND dob = ?", (name.strip(), dob)
            ).fetchone()
        return dict(row) if row else None

    def list_patients(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM patients ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(row) for row in rows]

    def get_slot(self, slot_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
        return dict(row) if row else None

    def list_slots(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM slots ORDER BY date, time, slot_id").fetchall()
        return [dict(row) for row in rows]

    def available_slots(self, reason: str | None = None, day: str | None = None,
                        specialty_id: str | None = None, doctor_id: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT s.* FROM slots s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM appointments a
                        WHERE a.slot_id = s.slot_id AND a.status = 'booked'
                    )"""
        args: list[Any] = []
        if reason:
            query += " AND s.reason = ?"
            args.append(reason)
        if day:
            query += " AND s.date = ?"
            args.append(day)
        if specialty_id:
            query += " AND s.specialty_id = ?"
            args.append(specialty_id)
        if doctor_id:
            query += " AND s.doctor_id = ?"
            args.append(doctor_id)
        query += " ORDER BY s.date, s.time, s.slot_id"
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
        return [dict(row) for row in rows]

    def list_appointments(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT a.appointment_id, a.patient_id, p.name AS patient_name,
                          a.slot_id, s.date, s.time, s.reason, s.provider,
                          s.specialty_id, s.specialty, s.doctor_id, s.clinic,
                          a.status, a.created_at
                   FROM appointments a
                   JOIN patients p ON p.patient_id = a.patient_id
                   JOIN slots s ON s.slot_id = a.slot_id"""
        args: tuple[Any, ...] = ()
        if patient_id:
            query += " WHERE a.patient_id = ?"
            args = (patient_id,)
        query += " ORDER BY s.date, s.time"
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
        return [dict(row) for row in rows]

    def cancel_appointment(self, patient_id: str, appointment_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE appointments SET status = 'cancelled' WHERE patient_id = ? AND appointment_id = ? AND status = 'booked'",
                (patient_id, appointment_id),
            )
        if cursor.rowcount != 1:
            return None
        return next((a for a in self.list_appointments(patient_id) if a["appointment_id"] == appointment_id), None)

    def reschedule_appointment(self, patient_id: str, appointment_id: str, new_slot_id: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                current = self._conn.execute(
                    """SELECT a.appointment_id, a.slot_id, s.doctor_id FROM appointments a
                       JOIN slots s ON s.slot_id = a.slot_id
                       WHERE a.patient_id = ? AND a.appointment_id = ? AND a.status = 'booked'""",
                    (patient_id, appointment_id),
                ).fetchone()
                new_slot = self._conn.execute("SELECT * FROM slots WHERE slot_id = ?", (new_slot_id,)).fetchone()
                if not current or not new_slot or new_slot["doctor_id"] != current["doctor_id"]:
                    self._conn.rollback()
                    return None
                occupied = self._conn.execute(
                    "SELECT 1 FROM appointments WHERE slot_id = ? AND status = 'booked'", (new_slot_id,)
                ).fetchone()
                if occupied:
                    self._conn.rollback()
                    return None
                self._conn.execute("UPDATE appointments SET slot_id = ? WHERE appointment_id = ?", (new_slot_id, appointment_id))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return next((a for a in self.list_appointments(patient_id) if a["appointment_id"] == appointment_id), None)

    def create_feedback(self, session_id: str, turn_id: str, rating: int, reason: str, comment: str | None = None) -> dict[str, Any]:
        feedback_id = f"F{secrets.token_hex(5).upper()}"
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO feedback (feedback_id, session_id, turn_id, rating, reason, comment, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (feedback_id, session_id, turn_id, rating, reason, comment, self._now()),
            )
        return {"feedback_id": feedback_id, "session_id": session_id, "turn_id": turn_id, "rating": rating, "reason": reason, "reviewed": False}

    def list_unreviewed_feedback(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT feedback_id, session_id, rating, reason, comment, created_at FROM feedback WHERE reviewed = 0 ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def review_feedback(self, feedback_id: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute("UPDATE feedback SET reviewed = 1 WHERE feedback_id = ?", (feedback_id,))
        return cursor.rowcount == 1

    def upcoming_opted_in_appointments(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT a.appointment_id, a.patient_id, p.name, p.contact, p.preferred_channel,
                          p.reminder_consent, s.date, s.time, s.provider, s.reason
                   FROM appointments a JOIN patients p ON p.patient_id = a.patient_id
                   JOIN slots s ON s.slot_id = a.slot_id
                   WHERE a.status = 'booked' AND p.reminder_consent = 1
                     AND p.preferred_channel != 'none' AND p.contact IS NOT NULL
                     AND s.date >= ? AND s.date <= ?
                   ORDER BY s.date, s.time""",
                (from_date, to_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def upcoming_patient_appointments(self, patient_id: str, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Return a patient's upcoming bookings for an on-screen, unsent reminder preview."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT a.appointment_id, a.patient_id, p.name AS patient_name,
                          s.date, s.time, s.provider, s.specialty, s.reason, s.clinic
                   FROM appointments a JOIN patients p ON p.patient_id = a.patient_id
                   JOIN slots s ON s.slot_id = a.slot_id
                   WHERE a.patient_id = ? AND a.status = 'booked' AND s.date >= ? AND s.date <= ?
                   ORDER BY s.date, s.time""",
                (patient_id, from_date, to_date),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _mask_contact(channel: str, contact: str) -> str:
        if channel == "email" and "@" in contact:
            name, domain = contact.split("@", 1)
            return f"{name[:1]}***@{domain}"
        digits = "".join(char for char in contact if char.isdigit())
        return f"***{digits[-4:]}" if digits else "***"

    def record_reminder_preview(self, appointment_id: str, channel: str, contact: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO reminder_runs (reminder_id, appointment_id, channel, recipient_masked, status, created_at) VALUES (?, ?, ?, ?, 'preview', ?)",
                (f"R{secrets.token_hex(5).upper()}", appointment_id, channel, self._mask_contact(channel, contact), self._now()),
            )
        return cursor.rowcount == 1

    def list_reminder_previews(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT r.reminder_id, r.appointment_id, r.channel, r.recipient_masked, r.status,
                          r.created_at, a.patient_id, p.name AS patient_name, s.date, s.time
                   FROM reminder_runs r JOIN appointments a ON a.appointment_id = r.appointment_id
                   JOIN patients p ON p.patient_id = a.patient_id JOIN slots s ON s.slot_id = a.slot_id
                   ORDER BY r.created_at DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def book_appointment(self, patient_id: str, slot_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                patient = self._conn.execute("SELECT 1 FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
                slot = self._conn.execute("SELECT * FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
                if not patient:
                    raise UnknownPatientError("Patient was not found")
                if not slot:
                    raise SlotUnavailableError("Slot was not found")
                occupied = self._conn.execute(
                    "SELECT 1 FROM appointments WHERE slot_id = ? AND status = 'booked'", (slot_id,)
                ).fetchone()
                if occupied:
                    raise SlotUnavailableError("Slot is no longer available")
                seq_row = self._conn.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name = 'appointments'"
                ).fetchone()
                appointment_id = f"A{(seq_row['seq'] if seq_row else 0) + 1:03d}"
                self._conn.execute(
                    """INSERT INTO appointments
                       (appointment_id, patient_id, slot_id, status, created_at)
                       VALUES (?, ?, ?, 'booked', ?)""",
                    (appointment_id, patient_id, slot_id, self._now()),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return next(item for item in self.list_appointments(patient_id) if item["appointment_id"] == appointment_id)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
