# Project status and decision log

**Snapshot:** 2026-10-08

**Purpose:** Distinguish the AI-assisted starting implementation from the directions and improvements requested by the project owner. Use the log template below for future changes so your reasoning and evidence stay visible.

## Project origin

The project owner set the original challenge: build a Python patient-appointment agent, use retrieval for clinic information, test hard scenarios as well as successful ones, and show an improvement loop. AI tools helped scaffold the first implementation. The features below reflect the project as it has evolved through owner-directed requests and iterative fixes; they should not be presented as proof that the owner personally wrote every implementation.

## Current feature map

| Area | Current implementation | Boundary / status |
|---|---|---|
| Patient entry | Local profile lookup/registration using name and DD/MM/YYYY date of birth; refresh returns to entry screen | Demo convenience only; not secure authentication or identity proof |
| Scheduling conversation | Multi-turn Python flow; clickable visit options and a guided day → specialty → doctor → slot path; dates generated from seven-day offsets | Fictional catalog and JSON slots; no live clinic calendar |
| Appointment actions | Book after a specific slot choice and explicit confirmation; list, reschedule with same doctor, and cancel | SQLite transactions protect demo availability; no EHR integration |
| ajCares.ai interface | React chat and appointment UI served by Vite; FastAPI backend | Run locally; Vite uses port 5173 and API uses 8000 |
| Specialist workflows | Appointment scheduler, read-only clinic information responder, and reminder preview worker | Three roles with different permissions and deterministic routing; no LangGraph or LLM supervisor |
| Policy RAG | Chroma persistent vector store with MiniLM ONNX embeddings when `requirements-rag.txt` is installed; keyword/IDF fallback otherwise | Small labeled retrieval set; similarity is not calibrated confidence |
| Local generation | Optional Hugging Face Qwen2.5-0.5B-Instruct Q4 GGUF for wording answers grounded in retrieved passages | About 398 MB, excluded from Git; cannot book or change appointments; deterministic fallback remains |
| Clinic directory | JSON catalog used for doctor/specialty facts | Fictional sample directory |
| Feedback | Thumbs rating, reason, optional comment; low ratings can be exported as review candidates | Human review only; feedback does not automatically train or alter live behavior |
| Reminder workflow | Finds upcoming opted-in appointments and records masked local previews | No SMS or email is sent |
| Safety/evaluation | Fixed scenarios inspect transcript, tool events, and resulting appointment state | Small demonstration suite, not a safety certification |

## Measured improvement example

The saved evaluation run starts with an ambiguous “yes” after multiple times are offered. Baseline: **9/11 checks (82%)**; the agent makes an unsupported booking claim, though the booking tool correctly writes no appointment. The harness records a structured rule requiring a specific slot, restated date/time, and explicit confirmation. Rerunning the same scenarios gives **11/11 (100%)**; the happy path still books exactly once. These scores describe only the included scenarios. See `artifacts/eval_report.json` and `artifacts/improvement.json`.

## Owner-directed evolution from the initial app

The project grew from a basic Python scheduling-agent/evaluation exercise into a local full-stack demo. The owner requested semantic vector search with embeddings, a light local model instead of a multi-gigabyte download, no more than three agents with genuinely separate uses, patient registration, feedback for future evaluation, and a polished React product named ajCares.ai. Later iterations added a click-first conversation, seven date-based choices, doctor/specialty selection, appointment editing and cancellation, feedback controls, reminder previews, and clearer policy-question flows. The evaluation demo was also explained around the ambiguous-yes failure and the concrete before/after reinforcement.

The core design judgment is to keep scheduling authority in explicit Python logic and narrow tools, while retrieval and the optional LLM are limited to policy answers. The workflow does not use LangGraph today; the project uses explicit Python state and deterministic routing. Future changes should be recorded as they are actually made, including alternatives and measured outcomes.

## AI and owner judgment

AI assistance helped scaffold code, UI, documentation, and suggested implementation options. The owner supplied the product direction and repeatedly corrected the experience based on observed problems, including form format, chat options, slot cards, reminders, and the desired setup/demo flow. The final distinction between requested features and personally implemented changes remains for the owner to update accurately.

## Future addition log

Copy this entry for each change you make. Write the observation and your reason in your own words; add evaluation evidence after testing.

```text
### YYYY-MM-DD — Short name of my addition

- Problem I observed:
- Why I think it happens:
- My proposed change and why:
- Alternatives I considered:
- What I changed:
- Scenarios/metrics checked:
- Before → after result:
- Regressions or new risks checked:
- What I learned / next question:
```
