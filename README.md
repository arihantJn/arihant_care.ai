# ajCares.ai

ajCares.ai is a local Python appointment-scheduling demo with a React chat interface, policy RAG, bounded specialist workflows, and a repeatable evaluation-improvement loop. It uses fictional data only; it is not a clinic system, secure login, or medical advice service.

## 1. Get the project

Get the project from the [arihantJn/arihant_care.ai GitHub repository](https://github.com/arihantJn/arihant_care.ai). Install Python 3.10 or newer and Node.js LTS (npm is included with Node.js).

**Option A — Git is installed:** open PowerShell in the folder where you want the project and run:

```powershell
git clone https://github.com/arihantJn/arihant_care.ai.git
cd arihant_care.ai
```

**Option B — no Git in the terminal:** open the [repository page](https://github.com/arihantJn/arihant_care.ai), select **Code → Download ZIP**, then extract the ZIP. Or download the [main-branch ZIP directly](https://github.com/arihantJn/arihant_care.ai/archive/refs/heads/main.zip). Open the extracted `arihant_care.ai-main` folder in VS Code. In either option, run the remaining commands from the project root (the folder containing `requirements.txt` and `web`).

## 2. Install Python dependencies

From the project root, create and activate a virtual environment, then install the required backend packages:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again. The base requirements install the API and scheduling demo. Optional RAG and model packages are separate so the basic app stays light.

## 3. Install frontend dependencies

Open a second PowerShell terminal in the project root. Check that Node and npm are available (`node --version` and `npm --version`), then install the React/Vite packages:

```powershell
cd web
npm install
```

If `npm` is not recognized, install Node.js LTS from [nodejs.org](https://nodejs.org/), close and reopen VS Code, and retry. Do not run a Vite JavaScript file directly; `npm run dev` is the supported frontend command.

## 4. Start the app

Keep two terminals open. Terminal 1 should be in the repository root. Activate the virtual environment if needed, then start the Python API:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn src.api:app --reload
```

Terminal 2 is already in the `web` folder from step 3. Start the frontend there:

```powershell
npm run dev
```

Open **http://127.0.0.1:5173/**. The Vite development server proxies `/api` calls to FastAPI on port 8000 and is configured to fail if port 5173 is already occupied. Stop each server with **Ctrl+C** in its own terminal. API documentation for developers is at **http://127.0.0.1:8000/docs**.

Each browser refresh returns to the local name and date-of-birth profile screen. Use fictional details. Choose a visit type and then select a day, specialty, doctor, and available time; the booking is only made after explicit confirmation. My appointments supports rescheduling with the same doctor and cancellation. Reminder previews are local and do not send messages.

## 5. Run the evaluation loop

From the repository root, with the virtual environment active:

```powershell
python -m src.eval_loop
```

The harness runs the same small scenarios before and after applying a structured reinforcement for the ambiguous “yes” failure. The saved demonstration reports 9/11 checks (82%) before and 11/11 (100%) after; these are results on the included toy suite, not a real-clinic safety claim. It checks conversation output, tool traces, and resulting appointment state. Reports are written under `artifacts/`.

## Demo recording

The end-to-end walkthrough is included in the repository: [Watch or download the demo video](assets/demo-walkthrough.mp4).

## Optional: semantic RAG with Chroma

The app can answer clinic-policy questions from the approved local policy files. Without Chroma, it uses its keyword/IDF fallback. To enable vector search and MiniLM embeddings:

```powershell
python -m pip install -r requirements-rag.txt
python -m src.retrieval_eval
$env:AJCARES_SEMANTIC_RAG='1'
python -m src.retrieval_eval
```

The first semantic run downloads Chroma's default `all-MiniLM-L6-v2` ONNX embedding model (about 79 MB) and stores the local vector index in `data/chroma/`. To explicitly select the fallback, set `$env:AJCARES_SEMANTIC_RAG='0'` in the backend terminal. The retrieval report compares recall@3, MRR@3, and out-of-scope abstention on a small labeled sample.

## Optional: lightweight local policy-answer wording

An optional Hugging Face Qwen2.5-0.5B-Instruct Q4 GGUF (about 398 MB) can phrase answers using retrieved policy passages. It cannot book, cancel, or choose appointment slots. On Windows, install a compatible CPU wheel and download the model:

```powershell
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python -m pip install huggingface-hub
python -m src.download_model
```

Some Python/Windows combinations may not have a compatible wheel; see the [llama-cpp-python install instructions](https://github.com/abetlen/llama-cpp-python#installation). The model file is intentionally not included in Git. To disable generation, set `$env:AJCARES_LLM_ENABLED='0'` before starting the backend; cited deterministic policy answers remain available.

## Other useful commands

Run feedback review export (low ratings become human-review candidates, not automatic behavior changes):

```powershell
python -m src.feedback_review
```

Run the text-only demo:

```powershell
python -m src.agent
```

## Project notes and limitations

- [PROJECT_STATUS.md](PROJECT_STATUS.md) records the starting point, requested additions, implementation status, and a template for documenting future changes.
- [design.txt](design.txt) summarizes the design, measured improvement loop, production gap, and AI-assisted versus human-directed choices.
- Python API: FastAPI. Frontend: React and Vite. Structured demo records: SQLite and JSON. Policy retrieval: Chroma vectors with MiniLM embeddings when the optional package is installed. The local Qwen model is optional. The workflow uses bounded Python components and explicit routing; it does not currently use LangGraph.
- SQLite database, vector index, model weights, and generated evaluation fixtures are local runtime files and are excluded from Git. The JSON files in `data/` are fictional seed data.
- Name and date of birth are only a demo profile lookup, not authentication. Do not use real patient information or expose the app to the internet. Production would require verified identity, access controls, a clinic-approved scheduling integration and policy source, audit/privacy controls, and much broader validation.
