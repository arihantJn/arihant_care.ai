"""Multi-turn, deterministic appointment agent with RAG for clinic policy answers."""
from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rag import PolicyRAG
from .information_agent import ClinicInformationAgent
from .tools import ClinicTools

EMERGENCY = ("chest pain", "can't breathe", "cannot breathe", "trouble breathing", "face drooping", "signs of stroke")


@dataclass
class Session:
    transcript: list[dict[str, str]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    finished: bool = False


class SchedulingAgent:
    def __init__(self, reinforced: bool | None = None, tools: ClinicTools | None = None, rag: PolicyRAG | None = None):
        self.tools = tools or ClinicTools()
        self.rag = rag or PolicyRAG()
        self.information_agent = ClinicInformationAgent(self.rag)
        rules = json.loads((Path(__file__).resolve().parents[1] / "data" / "reinforcements.json").read_text(encoding="utf-8"))
        self.reinforced = (any(r.get("id") == "specific_slot_before_confirmation" and r.get("enabled") for r in rules) if reinforced is None else reinforced)
        self.session = Session()

    def _say(self, text: str) -> str:
        self.session.transcript.append({"role": "assistant", "text": text})
        return text

    def reply(self, text: str) -> str:
        s = self.session
        if s.finished:
            return self._say("This scheduling conversation is complete. Start a new session for another request.")
        s.transcript.append({"role": "patient", "text": text})
        low = text.lower()
        if any(x in low for x in EMERGENCY):
            s.finished = True
            return self._say("Those symptoms may be an emergency. Please contact local emergency services now; don't wait for a clinic appointment.")
        # Route clear policy questions on every turn, even if a previous greeting
        # left the conversation in the lightweight "unknown" state.
        if (self.information_agent.is_directory_question(text)
                or any(x in low for x in ("hours", "timing", "open", "policy", "cancel", "reschedul", "privacy"))):
            return self._say(self.information_agent.reply(text))

        if low.strip() in {"check up", "check-up", "checkup", "follow up", "follow-up", "followup"}:
            s.state["intent"] = "schedule"
            s.state["reason"] = "follow-up" if "follow" in low else "checkup"

        if s.state.get("intent") == "unknown":
            s.state.pop("intent", None)
        if not s.state.get("intent"):
            s.state["intent"] = "schedule" if any(x in low for x in ("appointment", "book", "schedule", "checkup", "check up", "check-up", "follow-up", "follow up")) else "unknown"
            if s.state["intent"] == "schedule":
                s.state["reason"] = "follow-up" if "follow" in low else ("checkup" if "checkup" in low else None)
        if s.state["intent"] == "unknown":
            return self._say("I can help find a checkup or follow-up appointment, or answer clinic policy questions. What would you like to do?")

        if not s.state.get("reason"):
            if low.strip() in {"checkup", "check-up", "routine checkup", "1"}:
                s.state["reason"] = "checkup"
            elif low.strip() in {"follow-up", "follow up", "followup", "2"}:
                s.state["reason"] = "follow-up"
            elif "checkup" in low or "check up" in low or "check-up" in low:
                s.state["reason"] = "checkup"
            elif "follow" in low:
                s.state["reason"] = "follow-up"
            if not s.state["reason"]:
                return self._say("Please choose one of the visit types: Checkup or Follow-up.")
        if not s.state.get("patient"):
            # Standalone CLI/eval sessions may still verify a patient conversationally;
            # the web API preloads the already-authenticated patient in session state.
            if not s.state.get("patient_name"):
                if not s.state.get("awaiting_identity"):
                    s.state["awaiting_identity"] = True
                    return self._say("Please provide the patient's full name and date of birth (YYYY-MM-DD) so I can verify the record.")
                date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
                candidate = text[:date_match.start()].strip(" ,") if date_match else text.strip()
                if not candidate:
                    return self._say("Please provide the patient's full name so I can verify the record.")
                s.state["patient_name"] = candidate
            if not s.state.get("dob"):
                match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
                if match:
                    s.state["dob"] = match.group(1)
                else:
                    return self._say("What is the patient's date of birth in YYYY-MM-DD format?")
            patient = self.tools.verify_patient(s.state["patient_name"], s.state["dob"])
            if not patient:
                s.state.pop("patient_name", None)
                s.state.pop("dob", None)
                return self._say("I couldn't verify that combination. Please check the name and date of birth.")
            s.state["patient"] = patient
        if not s.state.get("slots"):
            slots = self.tools.find_availability(s.state["reason"])
            s.state["slots"] = slots
            if not slots:
                s.finished = True
                return self._say("I couldn't find an available slot for that visit type. Please contact the clinic for help.")
            s.state["awaiting_choice"] = len(slots) > 1
            choices = "; ".join(f"{x['slot_id']}: {x['date']} at {x['time']} with {x['provider']}" for x in slots[:3])
            return self._say(f"I found {len(slots)} available times. Choose one of the appointment cards below.")

        slots = s.state["slots"]
        chosen = next((slot for slot in slots if slot["slot_id"].lower() in low or slot["time"].lower() in low), None)
        if not s.state.get("selected_slot"):
            if chosen:
                token = self.tools.record_patient_choice(s.state["patient"], chosen["slot_id"], text)
                s.state["selected_slot"] = chosen
                s.state["selection_token"] = token
                s.state["awaiting_choice"] = False
                return self._say(f"Please review the selected time: {chosen['date']} at {chosen['time']} with {chosen['provider']}. Confirm to book it.")
            if self.reinforced:
                return self._say("Please choose one specific option by its slot ID or time before I can ask for confirmation.")
            # Deliberate baseline defect for the eval to discover and repair.
            if low.strip() in ("yes", "yeah", "sure", "ok", "okay") and len(slots) > 1:
                s.state["selected_slot"] = slots[0]
                s.state["unsafe_ambiguous_yes"] = True
                try:
                    self.tools.book_appointment(s.state["patient"], slots[0]["slot_id"], selection_token=None, confirmation_text=text)
                except ValueError:
                    pass
                s.finished = True
                return self._say(f"Your appointment is booked for {slots[0]['date']} at {slots[0]['time']}.")
            return self._say("Which specific slot would you like?")

        if low.strip() in ("yes", "yeah", "sure", "ok", "okay", "confirm", "i confirm"):
            chosen = s.state["selected_slot"]
            try:
                appt = self.tools.book_appointment(s.state["patient"], chosen["slot_id"], s.state.get("selection_token"), text)
            except ValueError:
                s.finished = True
                return self._say("That slot is no longer available. Please contact the clinic to choose another.")
            s.finished = True
            return self._say(f"Booked. Your appointment ID is {appt['appointment_id']}: {appt['date']} at {appt['time']} with {appt['provider']}.")
        s.state.pop("selected_slot", None)
        return self._say("I haven't booked anything. Which available slot would you prefer?")

    def chat(self) -> None:
        print("Clinic Scheduler (type 'quit' to end). This demo uses fictional records.")
        while not self.session.finished:
            user = input("You: ").strip()
            if user.lower() == "quit":
                break
            print("Agent:", self.reply(user))


def main() -> None:
    SchedulingAgent().chat()


if __name__ == "__main__":
    main()
