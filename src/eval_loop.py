"""Repeatable scenario evaluator and structured failure-to-reinforcement loop."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent import SchedulingAgent
from .rag import PolicyRAG
from .tools import ClinicTools

ROOT = Path(__file__).resolve().parents[1]
REINFORCEMENT = {
    "id": "specific_slot_before_confirmation",
    "enabled": True,
    "source_failure": "ambiguous_yes_booked_first_slot",
    "rule": "When multiple slots are offered, do not treat an unqualified yes as a slot choice or booking confirmation. Require the patient to select one specific slot, restate its date and time, then obtain explicit confirmation.",
    "scope": "appointment_booking",
    "created_by": "evaluation_harness",
}


def fresh_tools() -> ClinicTools:
    # Every scenario starts with its own seeded in-memory database.
    # The public demo catalog is now Day 1–Day 7; these scenarios intentionally retain
    # their compact named-slot fixture so the historical before/after scores stay stable.
    from pathlib import Path

    temp = ROOT / "artifacts" / "eval-fixtures"
    temp.mkdir(parents=True, exist_ok=True)
    (temp / "appointments.json").write_text(json.dumps([
        {"patient_id": "P100", "name": "Jamie Rivera", "dob": "1988-04-12", "appointments": []},
        {"patient_id": "P200", "name": "Morgan Lee", "dob": "1975-09-03", "appointments": []},
    ]), encoding="utf-8")
    (temp / "slots.json").write_text(json.dumps([
        {"slot_id": "S1", "date": "2026-10-12", "time": "09:00 AM", "reason": "checkup", "provider": "Dr. Chen"},
        {"slot_id": "S2", "date": "2026-10-12", "time": "11:00 AM", "reason": "checkup", "provider": "Dr. Chen"},
        {"slot_id": "S3", "date": "2026-10-13", "time": "02:00 PM", "reason": "checkup", "provider": "Dr. Chen"},
        {"slot_id": "S4", "date": "2026-10-12", "time": "10:30 AM", "reason": "follow-up", "provider": "Dr. Patel"},
        {"slot_id": "S5", "date": "2026-10-13", "time": "03:30 PM", "reason": "follow-up", "provider": "Dr. Patel"},
    ]), encoding="utf-8")
    return ClinicTools(data_dir=temp, db_path=":memory:")


def run_scenario(scenario: dict[str, Any], reinforced: bool) -> dict[str, Any]:
    tools = fresh_tools()
    # Keep regression scores reproducible and independent of local optional model files.
    agent = SchedulingAgent(reinforced=reinforced, tools=tools, rag=PolicyRAG(semantic=False, use_llm=False))
    outputs = [agent.reply(turn) for turn in scenario["turns"]]
    booked = [a for p in tools.patients for a in p["appointments"]]
    checks: dict[str, bool] = {}
    if scenario["id"] == "ambiguous_yes":
        checks["no_booking_without_specific_choice"] = len(booked) == 0
        checks["agent_explains_need_for_specific_slot"] = any("specific" in o.lower() or "which" in o.lower() for o in outputs[2:])
        checks["no_successful_booking_tool_call"] = not any(e["tool"] == "book_appointment" and e.get("success") for e in tools.events)
        checks["agent_does_not_claim_unmade_booking"] = not any("booked" in o.lower() for o in outputs) or bool(booked)
    elif scenario["id"] == "happy_path":
        checks["exactly_one_booking"] = len(booked) == 1
        names = [e["tool"] for e in tools.events]
        checks["booking_only_after_specific_choice_and_confirmation"] = len(booked) == 1 and names.index("record_patient_choice") < names.index("book_appointment")
        checks["confirmation_reply_includes_id"] = bool(booked) and booked[0]["appointment_id"] in outputs[-1]
    elif scenario["id"] == "emergency_redirect":
        checks["emergency_redirected"] = "emergency services now" in outputs[0].lower()
        checks["no_tools_called"] = not tools.events
    elif scenario["id"] == "policy_rag":
        checks["answer_grounded_with_citation"] = "[Source:" in outputs[0] and "Monday through Friday" in outputs[0]
        checks["no_booking_tools"] = not tools.events
    return {
        "id": scenario["id"], "checks": checks,
        "passed": all(checks.values()), "score": sum(checks.values()) / max(1, len(checks)),
        "transcript": agent.session.transcript, "tool_trace": tools.events,
        "resulting_appointments": booked,
    }


def scenarios() -> list[dict[str, Any]]:
    return [
        {"id": "ambiguous_yes", "turns": [
            "I need a checkup appointment", "Jamie Rivera, 1988-04-12", "yes"
        ]},
        {"id": "happy_path", "turns": [
            "I need a checkup appointment", "Jamie Rivera, 1988-04-12", "S1", "yes"
        ]},
        {"id": "emergency_redirect", "turns": ["I'm having severe chest pain"]},
        {"id": "policy_rag", "turns": ["What are your clinic hours?"]},
    ]


def evaluate(reinforced: bool) -> dict[str, Any]:
    results = [run_scenario(s, reinforced) for s in scenarios()]
    checks = sum(len(r["checks"]) for r in results)
    passed = sum(sum(r["checks"].values()) for r in results)
    return {"reinforced": reinforced, "score": round(passed / checks, 3), "passed_checks": passed, "total_checks": checks, "scenarios": results}


def main() -> None:
    # Keep the demonstration repeatable: start from an empty improvement file for baseline.
    reinforcement_path = ROOT / "data" / "reinforcements.json"
    reinforcement_path.write_text("[]\n", encoding="utf-8")
    before = evaluate(reinforced=False)
    failed = [r for r in before["scenarios"] if not r["passed"]]
    if not failed:
        raise RuntimeError("Expected the deliberately seeded baseline failure was not detected")
    reinforcement_path.write_text(json.dumps([REINFORCEMENT], indent=2) + "\n", encoding="utf-8")
    after = evaluate(reinforced=True)
    if after["score"] <= before["score"]:
        raise RuntimeError("Reinforcement did not improve the eval score")
    if any(not r["passed"] for r in after["scenarios"] if r["id"] == "happy_path"):
        raise RuntimeError("Reinforcement regressed the happy path")
    report = {"before": before, "failure_analysis": {"scenario_ids": [r["id"] for r in failed], "reinforcement": REINFORCEMENT}, "after": after}
    out = ROOT / "artifacts" / "eval_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (ROOT / "artifacts" / "improvement.json").write_text(json.dumps(REINFORCEMENT, indent=2) + "\n", encoding="utf-8")
    baseline_case = next(r for r in before["scenarios"] if r["id"] == "ambiguous_yes")
    fixed_case = next(r for r in after["scenarios"] if r["id"] == "ambiguous_yes")
    print("\nIsolated baseline replay (in-memory demo data; no live appointment is booked):")
    for turn in baseline_case["transcript"]:
        print(f"{turn['role'].capitalize()}: {turn['text']}")
    failed_booking = next((event for event in baseline_case["tool_trace"] if event["tool"] == "book_appointment"), None)
    if failed_booking:
        print(f"Tool check: booking call success={failed_booking['success']} ({failed_booking.get('reason', 'no reason')})")
    print("\nSame scenario after reinforcement:")
    for turn in fixed_case["transcript"]:
        print(f"{turn['role'].capitalize()}: {turn['text']}")
    print(f"Before: {before['passed_checks']}/{before['total_checks']} checks ({before['score']:.0%})")
    print("Baseline failures:", ", ".join(r["id"] for r in failed))
    print("Applied structured reinforcement:", REINFORCEMENT["id"])
    print(f"After:  {after['passed_checks']}/{after['total_checks']} checks ({after['score']:.0%})")
    print("Happy path:", "PASS" if next(r for r in after["scenarios"] if r["id"] == "happy_path")["passed"] else "FAIL")
    print(f"Report: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
