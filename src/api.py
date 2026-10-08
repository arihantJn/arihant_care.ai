"""Local HTTP API for the ajCares.ai chat UI and demo patient records."""
from __future__ import annotations

from datetime import date, timedelta
import json
import threading
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .agent import SchedulingAgent

from .database import ClinicDatabase, DuplicatePatientError
from .rag import shared_policy_rag
from .reminders import ReminderAgent

ROOT = Path(__file__).resolve().parents[1]
db = ClinicDatabase(seed_dir=ROOT / "data")
sessions: dict[str, SchedulingAgent] = {}
session_locks: dict[str, threading.RLock] = {}
session_patients: dict[str, dict] = {}
session_tokens: dict[str, str] = {}
auth_tokens: dict[str, str] = {}
catalog = json.loads((ROOT / "data" / "clinic_catalog.json").read_text(encoding="utf-8"))

app = FastAPI(
    title="ajCares.ai API",
    description="Local demo API for fictional patients and appointment scheduling.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


class PatientRegistration(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    dob: date
    contact: str | None = Field(default=None, max_length=200)
    preferred_channel: Literal["none", "email", "sms"] = "none"
    preferred_language: str = Field(default="en", min_length=2, max_length=30)
    reminder_consent: bool = False

    @model_validator(mode="after")
    def validate_registration(self) -> "PatientRegistration":
        if self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future")
        if self.reminder_consent and (self.preferred_channel == "none" or not self.contact):
            raise ValueError("Reminder consent requires a contact and preferred channel")
        if self.preferred_channel != "none" and not self.contact:
            raise ValueError("A contact value is required for the selected channel")
        return self


class PatientAccess(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    dob: date

    @model_validator(mode="after")
    def validate_dob(self) -> "PatientAccess":
        if self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return self


class SessionStart(BaseModel):
    auth_token: str = Field(min_length=20, max_length=80)


class SlotSelection(BaseModel):
    slot_id: str = Field(min_length=1, max_length=80)


class AppointmentChange(BaseModel):
    slot_id: str = Field(min_length=1, max_length=80)


class ChatMessage(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class PatientFeedback(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    turn_id: str = Field(min_length=1, max_length=80)
    rating: int = Field(ge=1, le=5)
    reason: Literal["helpful", "wrong_policy", "misunderstood", "confusing", "unsafe_action", "other"] = "other"
    comment: str | None = Field(default=None, max_length=500)


@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def create_chat_session(payload: SessionStart) -> dict[str, str]:
    patient_id = auth_tokens.get(payload.auth_token)
    patient = db.get_patient(patient_id) if patient_id else None
    if not patient:
        raise HTTPException(status_code=401, detail="Please sign in again to start a session.")
    session_id = str(uuid4())
    agent = SchedulingAgent(rag=shared_policy_rag())
    agent.session.state["patient"] = patient
    sessions[session_id] = agent
    session_locks[session_id] = threading.RLock()
    session_patients[session_id] = patient
    session_tokens.pop(session_id, None)
    return {
        "session_id": session_id,
        "assistant_message": f"Hi {patient['name']}, I’m ajCares. Choose Book appointment for a few quick selections, or ask me a clinic-policy question.",
    }


@app.post("/api/auth")
def patient_access(payload: PatientAccess) -> dict:
    patient = db.verify_patient(payload.name, payload.dob.isoformat())
    created = patient is None
    if created:
        patient = db.create_patient(payload.name, payload.dob.isoformat())
    token = str(uuid4())
    auth_tokens[token] = patient["patient_id"]
    return {"auth_token": token, "patient": {"patient_id": patient["patient_id"], "name": patient["name"]}, "created": created}


@app.get("/api/scheduling/days")
def scheduling_days() -> list[dict]:
    slots = db.available_slots()
    valid_dates = {(date.today() + timedelta(days=i)).isoformat() for i in range(7)}
    visible_slots = [slot for slot in slots if slot["date"] in valid_dates]
    days = sorted({slot["date"] for slot in visible_slots})
    return [{"id": day, "label": date.fromisoformat(day).strftime("%a, %d %b"), "available_slots": sum(1 for slot in visible_slots if slot["date"] == day)} for day in days]


@app.get("/api/scheduling/specialties")
def scheduling_specialties(day: str = Query(min_length=1)) -> list[dict]:
    if day not in {(date.today() + timedelta(days=i)).isoformat() for i in range(7)}:
        raise HTTPException(status_code=404, detail="Choose one of the next seven demo days.")
    available = {slot["specialty_id"] for slot in db.available_slots(day=day)}
    return [{"id": item["id"], "name": item["name"], "description": item["description"]}
            for item in catalog["specialties"] if item["id"] in available]


@app.get("/api/scheduling/doctors")
def scheduling_doctors(day: str = Query(min_length=1), specialty_id: str = Query(min_length=1)) -> list[dict]:
    if day not in {(date.today() + timedelta(days=i)).isoformat() for i in range(7)} or specialty_id not in {x["id"] for x in catalog["specialties"]}:
        raise HTTPException(status_code=404, detail="That day or specialty is not in the demo catalog.")
    available = db.available_slots(day=day, specialty_id=specialty_id)
    doctor_ids = {slot["doctor_id"] for slot in available}
    return [{**doctor, "available_slots": sum(1 for slot in available if slot["doctor_id"] == doctor["id"])}
            for doctor in catalog["doctors"] if doctor["id"] in doctor_ids]


@app.get("/api/scheduling/slots")
def scheduling_slots(day: str = Query(min_length=1), specialty_id: str = Query(min_length=1),
                     doctor_id: str = Query(min_length=1)) -> list[dict]:
    if (day not in {(date.today() + timedelta(days=i)).isoformat() for i in range(7)}
            or specialty_id not in {x["id"] for x in catalog["specialties"]}
            or doctor_id not in {x["id"] for x in catalog["doctors"]}):
        raise HTTPException(status_code=404, detail="That day, specialty, or doctor is not in the demo catalog.")
    return db.available_slots(day=day, specialty_id=specialty_id, doctor_id=doctor_id)


@app.post("/api/sessions/{session_id}/select-slot")
def select_booking_slot(session_id: str, payload: SlotSelection) -> dict:
    agent = sessions.get(session_id)
    patient = session_patients.get(session_id)
    if not agent or not patient:
        raise HTTPException(status_code=404, detail="Session expired. Please sign in again.")
    slot = db.get_slot(payload.slot_id)
    available = {item["slot_id"] for item in db.available_slots()}
    if not slot or payload.slot_id not in available:
        raise HTTPException(status_code=409, detail="That time is no longer available. Please choose another.")
    try:
        token = agent.tools.record_patient_choice(patient, slot["slot_id"], f"I choose slot {slot['slot_id']} at {slot['time']}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session_tokens[session_id] = token
    return {"slot": slot, "message": "Please review the details and confirm to book."}


@app.post("/api/sessions/{session_id}/confirm")
def confirm_booking(session_id: str, payload: SlotSelection) -> dict:
    agent = sessions.get(session_id)
    patient = session_patients.get(session_id)
    token = session_tokens.get(session_id)
    if not agent or not patient or not token:
        raise HTTPException(status_code=409, detail="Choose an available time before confirming.")
    try:
        appointment = agent.tools.book_appointment(patient, payload.slot_id, token, "yes")
    except ValueError as exc:
        session_tokens.pop(session_id, None)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session_tokens.pop(session_id, None)
    return {"appointment": appointment}


@app.post("/api/sessions/{session_id}/messages")
def send_chat_message(session_id: str, payload: ChatMessage) -> dict:
    agent = sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session expired. Start a new conversation.")
    with session_locks.setdefault(session_id, threading.RLock()):
        answer = agent.reply(payload.text.strip())
        pending_slots = agent.session.state.get("slots", []) if agent.session.state.get("awaiting_choice") else []
        selected = agent.session.state.get("selected_slot")
    return {"assistant_message": answer, "finished": agent.session.finished,
            "slot_choices": pending_slots, "selected_slot": selected}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ajCares.ai API", "mode": "local-demo"}


@app.post("/api/patients", status_code=status.HTTP_201_CREATED)
def register_patient(payload: PatientRegistration) -> dict:
    try:
        return db.create_patient(
            name=payload.name,
            dob=payload.dob.isoformat(),
            contact=payload.contact,
            preferred_channel=payload.preferred_channel,
            preferred_language=payload.preferred_language,
            reminder_consent=payload.reminder_consent,
        )
    except DuplicatePatientError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str) -> dict:
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    patient.pop("created_at", None)
    return patient


@app.get("/api/patients/{patient_id}/appointments")
def list_patient_appointments(patient_id: str) -> list[dict]:
    if not db.get_patient(patient_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return db.list_appointments(patient_id)


def _session_patient(session_id: str) -> dict:
    patient = session_patients.get(session_id)
    if not patient or not sessions.get(session_id):
        raise HTTPException(status_code=404, detail="Session expired. Please sign in again.")
    return patient


@app.get("/api/sessions/{session_id}/appointments")
def list_signed_in_appointments(session_id: str) -> list[dict]:
    patient = _session_patient(session_id)
    return [a for a in db.list_appointments(patient["patient_id"]) if a["status"] == "booked"]


@app.post("/api/sessions/{session_id}/appointments/{appointment_id}/cancel")
def cancel_signed_in_appointment(session_id: str, appointment_id: str) -> dict:
    patient = _session_patient(session_id)
    appointment = db.cancel_appointment(patient["patient_id"], appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="That active appointment was not found for your profile.")
    return {"appointment": appointment}


@app.post("/api/sessions/{session_id}/appointments/{appointment_id}/reschedule")
def reschedule_signed_in_appointment(session_id: str, appointment_id: str, payload: AppointmentChange) -> dict:
    patient = _session_patient(session_id)
    current = next((a for a in db.list_appointments(patient["patient_id"])
                    if a["appointment_id"] == appointment_id and a["status"] == "booked"), None)
    if not current:
        raise HTTPException(status_code=404, detail="That active appointment was not found for your profile.")
    slot = db.get_slot(payload.slot_id)
    if not slot or slot["doctor_id"] != current["doctor_id"]:
        raise HTTPException(status_code=400, detail="Choose an available time with the same doctor.")
    updated = db.reschedule_appointment(patient["patient_id"], appointment_id, payload.slot_id)
    if not updated:
        raise HTTPException(status_code=409, detail="That time is no longer available. Please choose another.")
    return {"appointment": updated}


@app.get("/api/slots")
def list_available_slots(
    reason: Literal["checkup", "follow-up"] | None = None,
    day: date | None = Query(default=None, alias="date"),
) -> list[dict]:
    return db.available_slots(reason=reason, day=day.isoformat() if day else None)


@app.post("/api/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(payload: PatientFeedback) -> dict:
    if payload.session_id not in sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    safe_comment = payload.comment.strip() if payload.comment else None
    return db.create_feedback(payload.session_id, payload.turn_id, payload.rating, payload.reason, safe_comment)


@app.get("/api/feedback/review-queue")
def feedback_review_queue() -> list[dict]:
    # Local demonstration endpoint; keep FastAPI bound to localhost.
    return db.list_unreviewed_feedback()


@app.post("/api/reminders/preview")
def preview_reminders(days_ahead: int = Query(default=2, ge=0, le=30)) -> dict:
    previews = ReminderAgent(db).preview(days_ahead=days_ahead)
    return {"mode": "preview_only", "count": len(previews), "reminders": previews}


@app.post("/api/sessions/{session_id}/reminders/preview")
def preview_patient_reminders(session_id: str, days_ahead: int = Query(default=7, ge=0, le=30)) -> dict:
    patient = _session_patient(session_id)
    today = date.today()
    appointments = db.upcoming_patient_appointments(
        patient["patient_id"], today.isoformat(), (today + timedelta(days=days_ahead)).isoformat()
    )
    reminders = [{
        "appointment_id": item["appointment_id"],
        "message": f"Reminder preview (not sent): {item['patient_name']}, your appointment with {item['provider']} is on {date.fromisoformat(item['date']).strftime('%a, %d %b %Y')} at {item['time']} at {item['clinic']}.",
    } for item in appointments]
    return {"mode": "preview_only", "count": len(reminders), "reminders": reminders}
