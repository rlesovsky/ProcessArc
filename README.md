# ProcessArc

ProcessArc is the document-automation tool for UFP Industries wood treatment SCADA projects. It reads the UFP-supplied sequence workbook, discovers the plant configuration, extracts the device list (via the Claude API for prose, direct read for tables), runs a mandatory human review, and exports three deliverables: the Ignition IO list, the Cause & Effect draft, and a structured Treating Sequence Word document.

Phase 1 is UFP-specific by design. It runs as two local processes (Python backend + React frontend) on a single engineer's machine. There is no hosted server, no shared instance, and no Docker. See `docs/Automation_Tool_Phase1_Plan.md` for the full design.

---

## Project layout

```
ProcessArc/
├── backend/        Python + FastAPI — the pipeline
├── frontend/       React + Vite + TypeScript — the wizard UI
├── docs/           Design docs + per-project read files
├── templates/      UFP IO-list templates
├── projects/       Per-project working files (state.json, uploads, outputs)
└── README.md       this file
```

---

## Prerequisites

- **Python** 3.10 or later
- **Node.js** 18 or later (for the frontend)
- **An Anthropic API key** — required only when running real device extraction. Most of the pipeline runs offline; only sequence prose ever leaves the machine, and only at the Extract stage.

The key is saved through the Settings screen in the running app, not committed to the repo. See "API key" below.

---

## Setup

One-time, from the project root:

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # creates the local config; API key is added through the UI
cd ..

# Frontend
cd frontend
npm install
cd ..
```

`backend/.env` is git-ignored. The included `.env.example` shows the variables ProcessArc reads: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `PROJECTS_DIR`, `TEMPLATES_DIR`.

---

## Run

ProcessArc runs as two processes. Open two terminals.

**Terminal 1 — backend:**

```bash
cd backend
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000
```

Run from the **project root** (not from inside `backend/`) so `backend.api.main` resolves. The `--reload` flag picks up Python file changes without a restart; a saved API key takes effect immediately without reload either (the settings cache re-reads on every PUT/DELETE).

The backend serves at `http://127.0.0.1:8000`. The interactive API docs are at `http://127.0.0.1:8000/docs`.

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

The Vite dev server serves at `http://localhost:5173`. Open that in a browser. The frontend proxies API calls to the backend on port 8000.

---

## Using the tool

The frontend is a five-step wizard, enforced in order:

1. **Configure** — upload the UFP sequence workbook and the UFP IO template. The C&E profile is optional.
2. **Discover** — confirm the discovered Plant Configuration (cylinders, mix systems, tanks). Idle cylinders are flagged here, not assumed.
3. **Extract** — runs locally for the Chemical & Tank tables and via the Claude API for sequencing prose. Each sheet is its own task with its own retry. Failures surface clearly; the pipeline never silently produces an empty device list.
4. **Review** — the mandatory device-grid checkpoint. Confirm, edit, exclude, or add devices. Continue is gated on every flagged device being resolved.
5. **Export** — three result cards: IO list (`.xlsx`), C&E draft (`.xlsx`), Treating Sequence (`.docx`).

Useful query params:

- `?demo=discover` renders the Discover screen with a Fairless Hills stand-in (no upload required).
- `?dry_run=true` on the Extract POST uses a synthetic extractor — no network, no API key, no real data leaves the machine. Useful for UI work and for the period while the UFP data-policy sign-off is still open (Plan §13 Q6).

---

## API key

The Anthropic key is set, cleared, and inspected through the **Settings** UI in the running app.

- The backend stores it in `backend/.env` and never sends the raw key to the frontend.
- The frontend only ever sees a `configured` flag and a masked tail (`sk-ant-…ABCD`).
- A header status dot mirrors `/health`'s `has_api_key`: green when set, amber when not.
- Saving and clearing both reload the in-process settings cache, so changes take effect without restarting uvicorn.

`backend/.env` is read **ahead of** OS environment variables, so a stale exported `ANTHROPIC_API_KEY` from another app on your machine cannot shadow a UI-saved key.

---

## Data boundary

This is worth understanding before pointing the tool at real customer documents.

The only data that leaves the machine is **the sequence prose** for each cylinder and mix sheet, sent to the Claude API at Extract time. Everything else — workbook ingest, the Chemical & Tank tables, plant discovery, template reading, the Review grid, the exports — runs locally with no external call.

If the UFP data-policy sign-off for sending prose to the Claude API is still open for your project, run the Extract stage with `?dry_run=true` until it's resolved. The Plan calls this out as Open Q6.

---

## Tests

From the project root, with the backend venv activated:

```bash
pytest                                      # full pytest suite
python -m backend.tests.smoke_fairless      # smoke test against the real workbook
```

The smoke test expects `Fairless Hills Graphics and Sequence.xlsx` to be reachable; see the file's docstring for the path it checks.

---

## Where to find more

- **`docs/Automation_Tool_Phase1_Plan.md`** — what ProcessArc does. The design source of truth, written before the build. Section numbering is referenced throughout the codebase (`§8.3`, `§9A`, etc.).
- **`docs/ProcessArc_Technical_Architecture.md`** — how ProcessArc is built. Stack, backend module map, data flow.
- **`docs/ProcessArc_UI_Specification.md`** — the frontend's five screens and component breakdown.
- **`docs/Build_Status.md`** — current as-built state, divergences from the plan, open items.
- **`docs/Fairless_Hills_Project_ReadFile.md`** / **`docs/Hampton_Project_ReadFile.md`** — per-customer read files used as ground truth for the two plants ProcessArc has been tested against.

The three design docs were written before the build and are preserved as the record of why ProcessArc is the way it is. For *current state*, read `Build_Status.md`.

---

*ProcessArc — Texas Automation Systems / Randy*
