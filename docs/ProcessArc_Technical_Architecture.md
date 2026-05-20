# ProcessArc — Technical Architecture
## Companion to the Phase 1 Plan
**Project:** ProcessArc — UFP wood treatment project automation tool
**Scope of this document:** Technical architecture — stack, structure, and how the pieces communicate
**Author:** Texas Automation Systems / Randy
**Status:** Architecture design — no code
**Revision:** 2 — adds the Plant Configuration component, in step with Plan Revision 4
**Companion document:** `Automation_Tool_Phase1_Plan.md` (Revision 4)

---

## 0. How This Document Relates to the Plan

The Phase 1 Plan describes **what ProcessArc does** — the pipeline, the Plant Configuration, the Device Model, the two features, the scope. This document describes **how ProcessArc is built** — the languages, the components, the API boundary, the project layout, and the data flow.

Read the plan first. Nothing here changes the plan; it implements it. Where this document references a stage, component, or feature, it is the same one defined in the plan.

**Revision 2 note:** This revision adds the **Plant Configuration** component, matching Plan Revision 4. Plant configuration — how many cylinders and mixing systems a UFP plant has, and their actual numbers — is discovered from the input workbook, never assumed. The Hampton example proved this is necessary (cylinders numbered 1 and 3, one mix system instead of two).

---

## 1. Technology Stack — Decision and Reasoning

| Layer | Choice | Why |
|-------|--------|-----|
| Backend language | **Python** | The entire data layer lives here — `openpyxl` for reading/writing the Excel workbooks, the Anthropic SDK for Claude API calls, file handling. No real alternative for Excel manipulation plus LLM orchestration. |
| Backend framework | **FastAPI** | Modern, fast, first-class file-upload support, automatic interactive API documentation. Useful when one person builds both halves. |
| Frontend language | **React** (JavaScript/TypeScript) | The frontend's hardest job is the interactive device-review grid. React is built for stateful interactive UIs like this. TypeScript recommended for catching mistakes early. |
| Frontend tooling | **Vite** | Fast dev server and build tool for the React app. |
| Frontend UI components | A component library (e.g. shadcn/ui, Material UI, or similar) | So tables, buttons, dialogs, and the file browser are not hand-built. Pick one and stay with it. |
| Excel I/O | **openpyxl** | Already proven against all four source workbooks. Reads embedded structure, writes while preserving headers and metadata rows. |
| LLM access | **Anthropic Python SDK** | Official SDK for the Claude API. Called only from the backend. |

**The short version:** Python + React is the correct stack. Python is non-negotiable for the backend because of the Excel and LLM ecosystem. React is the right choice for the frontend because of the review screen.

---

## 2. The Critical Distinction — Two Different "APIs"

The word "API" refers to two completely separate things in ProcessArc. Conflating them causes real problems, so this is stated plainly:

### 2.1 ProcessArc's own API (the backend)
The FastAPI service that ProcessArc itself runs. The React frontend talks **to this**. Uploading a file "through the API" means the browser sends the file to this backend.

### 2.2 The Claude API (Anthropic's service)
Anthropic's hosted service. ProcessArc's **backend** calls **this** to perform prose device extraction (Plan, Section 8).

### 2.3 The Rule That Must Not Be Broken
**The React frontend never calls the Claude API directly. Only the ProcessArc backend calls the Claude API.**

The reason is the API key. If the frontend called Claude directly, the key would be embedded in the browser, where anyone inspecting the page could read it. The key lives on the backend only — environment variable or local settings file, never in frontend code, never sent to the browser. Same requirement as Plan Section 8.3.

```
   ALLOWED                              NOT ALLOWED
   -------                              -----------
   Browser → ProcessArc backend         Browser → Claude API directly
   ProcessArc backend → Claude API      (exposes the API key)
```

---

## 3. Deployment Model — Local Tool, Not a Hosted Web App

ProcessArc is a **local, single-user desktop-style tool**. It runs on the engineer's own machine for their own projects. It is not a public website.

Concrete benefits:
- **UFP customer documents never leave the engineer's machine** except for the sequence prose sent to the Claude API (Plan, Section 8.3). There is no hosted ProcessArc server.
- **The Claude API key stays on the local machine.** It never sits on a public server.
- **Simpler to build and run.** No hosting, no user accounts, no cloud infrastructure for Phase 1.

In practice: the engineer starts the ProcessArc backend on their machine, opens the React frontend in a browser pointed at `localhost`, and works. Both run locally.

**Future packaging (not Phase 1):** the Python backend and React frontend can later be wrapped together with Tauri or Electron for a double-click installed app. Deferred — Phase 1 runs locally as two processes.

---

## 4. The Two Components

### 4.1 ProcessArc Backend (Python / FastAPI)
The backend owns all logic and all data handling. Its responsibilities:
- Accept file uploads from the frontend (sequence workbook, UFP IO-list template, UFP C&E profile).
- Read the supplied template and build the template map (Plan, Section 7).
- **Discover the Plant Configuration** — count cylinders and mixing systems, capture their actual numbers and idle status (Plan, Section 6A).
- Ingest the sequence workbook (Plan, Stage 1).
- Run table extraction directly (Chemical and Tank sheet).
- Call the Claude API for prose extraction (Plan, Stage 2 / Section 8).
- Assemble candidate device records and hold the Project Device Model.
- Accept the engineer's review corrections (including Plant Configuration confirmation) and update the model.
- Render Feature 1 (IO list) and Feature 2 (C&E draft) into the supplied templates, sized to the Plant Configuration (Plan, Stages 4–5).
- Serve the finished files back to the frontend for download.
- Hold the Claude API key — and nothing else holds it.

### 4.2 ProcessArc Frontend (React)
The frontend is the engineer's window into the tool. It owns presentation and interaction, never logic. Its responsibilities:
- **File browser / upload screen** — pick and upload the sequence workbook and the UFP template files.
- **Plant Configuration confirmation screen** — show the discovered cylinders and mixing systems (with their actual numbers and any idle ones) for the engineer to confirm before extraction results are trusted (Plan, Section 6A.5).
- **Progress / status display** — show which pipeline stage is running.
- **The device review grid** — the most important screen. An interactive table of every extracted device, grouped by system and class, with confidence flags. The engineer confirms, renames, reclassifies, deletes false positives, adds missed devices, marks not-installed devices as excluded. Where the V9 / MS-valve / idle-cylinder cases get handled.
- **Export / download screen** — trigger the two exports and download the resulting IO list and C&E draft.

The frontend never reads Excel, never calls Claude, never holds the API key.

---

## 5. End-to-End Data Flow

The full request flow for one project, mapped onto the Plan's pipeline stages.

```
┌─────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND  (browser, localhost)                             │
│                                                                   │
│  1. Engineer uploads:                                             │
│       - UFP sequence workbook (Fairless Hills or Hampton, etc.)   │
│       - UFP IO-list template                                      │
│       - UFP C&E profile                                           │
└───────────────────────────┬───────────────────────────────────────┘
                            │  HTTP upload
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  PROCESSARC BACKEND  (Python / FastAPI, localhost)                │
│                                                                   │
│  Stage 0   Read template → build template map                    │
│  Stage 0A  DISCOVER PLANT CONFIGURATION                           │
│            count cylinders + mix systems from sheet names         │
│            capture actual numbers (e.g. Cyl 1 & 3), idle status   │
│  Stage 1   Ingest sequence workbook (all sheets)                  │
│  Stage 2   Table extraction (Chemical & Tank) — direct, no API    │
│            Prose extraction (the sequencing sheets found):        │
│                                                                   │
│               ┌──────────────────────────────┐                   │
│               │  CALL ──► CLAUDE API          │                   │
│               │  send sequence prose          │                   │
│               │  ◄── structured device JSON   │                   │
│               └──────────────────────────────┘                   │
│                                                                   │
│            Assemble candidate Device Records                      │
└───────────────────────────┬───────────────────────────────────────┘
                            │  Plant Configuration + candidate device list (JSON)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND                                                   │
│                                                                   │
│  Stage 3  REVIEW (mandatory)                                      │
│           3a. Confirm Plant Configuration                         │
│               "cylinders 1 & 3, one mix system" — yes/correct     │
│           3b. REVIEW GRID                                         │
│               confirm / edit / add / exclude devices              │
│               e.g. add V9, exclude MS valves, exclude idle Cyl 2  │
└───────────────────────────┬───────────────────────────────────────┘
                            │  confirmed config + corrected device list (JSON)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  PROCESSARC BACKEND                                               │
│                                                                   │
│  Stage 4  Build the final Project Device Model                    │
│  Stage 5  Render Feature 1 — IO list into the UFP template        │
│           Render Feature 2 — C&E draft, columns sized to the      │
│                              Plant Configuration                  │
└───────────────────────────┬───────────────────────────────────────┘
                            │  finished .xlsx files
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND                                                   │
│                                                                   │
│  Download:  {Site}_Ignition_IOList.xlsx                           │
│             {Site}_CauseAndEffect_Draft.xlsx                      │
└─────────────────────────────────────────────────────────────────┘
```

Stage 0A is new in this revision. The Claude API is still touched **once**, inside Stage 2, by the backend only. Every other stage runs locally with no external call — including Plant Configuration discovery, which reads sheet names and tables, not the LLM.

---

## 6. Backend Internal Structure

The backend is organized so the Phase 1 Plan's components map to clear, separable parts. Conceptual modules, not a file listing.

| Module | Responsibility | Plan Reference |
|--------|---------------|----------------|
| API layer | FastAPI endpoints — receive uploads, return results, expose pipeline stages | — |
| Template Reader | Read the UFP template workbook, build the template map | Plan §7 |
| **Plant Configuration Discovery** | Inspect workbook sheets + Chemical/Tank tables; build the list of cylinders and mix systems with actual numbers and idle status | Plan §6A |
| Workbook Ingester | Open the sequence workbook, separate prose sheets from table sheets | Plan Stage 1 |
| Table Extractor | Read the Chemical & Tank sheet into Tank and instrument records | Plan §9.2 Step E |
| Prose Extractor (pluggable) | Send prose to Claude, parse structured device JSON. Behind a fixed interface so a future P&ID extractor can be added | Plan §8.4 |
| Device Model | The canonical device data structure; source-agnostic; carries the real System Number | Plan §6 |
| Naming Rule Engine | Convert canonical devices into Ignition and C&E names using each device's own number/name | Plan §6.2 |
| Cause Library / C&E Profile | The UFP cause patterns and C&E layout rules; columns sized to the Plant Configuration | Plan §10 |
| IO List Exporter | Render the Device Model into the UFP IO-list template | Plan §9 |
| C&E Exporter | Render the C&E draft following the UFP profile, sized to the plant | Plan §10 |
| Settings | Holds the Claude API key and configuration; outside project data | Plan §8.3 |

Two structural decisions matter most:
- **The Prose Extractor behind a fixed interface** — lets the future P&ID extractor (Plan §15) slot in without disturbing anything else.
- **Plant Configuration Discovery as its own module, run before extraction** — every downstream module reads the Plant Configuration rather than assuming a plant shape. This is what makes Hampton (cylinders 1 and 3, one mix system) work without special-casing.

---

## 7. Suggested Project Layout

Backend and frontend are separate top-level folders so the two halves stay cleanly divided.

```
ProcessArc/
│
├── backend/                  Python / FastAPI
│   ├── api/                  FastAPI endpoints
│   ├── config/               Plant Configuration discovery
│   ├── ingest/               workbook ingester
│   ├── extract/              table extractor + pluggable prose extractor
│   ├── model/                the Device Model
│   ├── naming/               naming rule engine
│   ├── profiles/             UFP C&E profile + cause library
│   ├── export/               IO list exporter + C&E exporter
│   ├── settings/             config + API key handling (key NOT committed)
│   └── (entry point)
│
├── frontend/                 React / Vite
│   ├── src/
│   │   ├── pages/             upload, plant-config confirm, review, export
│   │   ├── components/        the device review grid, file browser, etc.
│   │   └── api/               functions that call the ProcessArc backend
│   └── (config)
│
├── templates/                UFP template files (IO-list template, C&E profile)
│
├── projects/                 per-project working files (kept local)
│
└── docs/                     this document, the Phase 1 plan, the read files
```

Notes:
- `backend/config/` is the Plant Configuration discovery module — new in this revision.
- The API key is **never** committed. It lives in an environment variable or a local-only ignored settings file.
- `projects/` holds in-progress and finished files for each UFP site. Local only.
- `templates/` is the small UFP template library raised as Open Question 8 in the Plan.

---

## 8. How the Frontend and Backend Communicate

The two components talk over plain HTTP on `localhost`. The frontend makes requests; the backend responds with JSON or files.

Conceptual endpoints (named by purpose, not final URLs):

| Purpose | Direction | Carries |
|---------|-----------|---------|
| Upload project files | Frontend → Backend | Sequence workbook, UFP template, C&E profile |
| Run discovery + extraction | Frontend → Backend | Trigger; backend runs Stages 0, 0A, 1, 2 |
| Get Plant Configuration | Backend → Frontend | The discovered cylinders/mix systems for confirmation |
| Get candidate device list | Backend → Frontend | The extracted devices for the review grid |
| Submit confirmed config + corrections | Frontend → Backend | The confirmed Plant Configuration and the engineer's edited device list |
| Run export | Frontend → Backend | Trigger; backend runs Stages 4–5 |
| Download results | Backend → Frontend | The finished IO list and C&E draft files |

The interface between the two halves is small and stable. The frontend sends triggers and data and displays results; it does not need to know how discovery, extraction, or export work internally.

---

## 9. Cross-Cutting Concerns

### 9.1 API Key Handling
The Claude API key is supplied once by the engineer and stored on the local machine — environment variable or a local settings file, never committed, never sent to the frontend. Hard rule, restated from Plan §8.3.

### 9.2 Handling Claude API Failures
API calls can fail — network drop, rate limit, timeout. The backend catches these, reports a clear message to the frontend, and lets the engineer retry. It must **never** silently produce an empty device list on a failed call (Plan §8.3).

### 9.3 Customer Data Boundary
Only the sequence **prose** is sent to the Claude API — not the whole workbook, not the embedded graphics, not the template files. Plant Configuration discovery, template reading, and table extraction all run locally with no external call. This is the boundary the engineer confirms acceptable per the UFP agreement (Plan, Open Question 6).

### 9.4 The Review Step Is Mandatory
The architecture does not allow a path from extraction straight to export. The review stage sits between Stage 2 and Stage 4 by design — and it now has two parts: confirming the Plant Configuration, then reviewing the device list. Export only runs on a confirmed configuration and a confirmed device list.

### 9.5 Plant Variability Is Handled by Discovery, Not Special Cases
There is no code branch for "two cylinders" versus "cylinders 1 and 3." The Plant Configuration Discovery module reads the actual shape from the workbook, and every downstream module is driven by that result. Adding a future UFP plant with four cylinders, or one mix system, or non-sequential numbering requires no code change — only that the workbook's sheets name the systems clearly enough to be discovered.

### 9.6 Keeping the P&ID Future Open
Three structural choices protect the future P&ID capability (Plan §15):
- The Prose Extractor sits behind a fixed interface — a future P&ID extractor is just another implementation behind it.
- The Device Model carries a Source Type field and is source-agnostic.
- Plant Configuration Discovery is independent of *how* the configuration was found — a future P&ID-based project could discover its configuration from the drawing set and feed the same downstream pipeline.

None of these cost anything in Phase 1; all prevent a rewrite later.

---

## 10. Suggested Build Order (Architecture View)

This complements the Plan's build order (Plan §14), viewed through the architecture.

1. **Backend skeleton** — FastAPI app that starts and responds. Settings module with API key handling.
2. **Device Model** — the canonical data structure, including System Number and Source Type.
3. **Plant Configuration Discovery** — count cylinders and mix systems from the workbook; the foundation everything downstream reads.
4. **Template Reader** — read a UFP template, produce the template map.
5. **Workbook Ingester + Table Extractor** — read the sequence workbook and the Chemical & Tank tables.
6. **Prose Extractor** — the Claude API call behind the pluggable interface.
7. **Frontend skeleton** — React app with upload screen, talking to the backend.
8. **Plant Configuration confirmation screen** — the first review step.
9. **Review grid** — the interactive device table; the largest frontend piece.
10. **IO List Exporter** — Feature 1; test against the real UFP Ignition file, then against Hampton.
11. **Cause Library + C&E Exporter** — Feature 2; test against the real UFP C&E sheet, then against Hampton's differing shape.

Build the backend pipeline first, then the frontend on top of it. Each backend module is testable on its own before any UI exists. The Hampton tests in steps 10 and 11 specifically prove the plant-variability handling.

---

*Document prepared by: Texas Automation Systems / Randy*
*ProcessArc technical architecture — design only, no implementation*
*Revision 2 — adds the Plant Configuration component; companion to Automation_Tool_Phase1_Plan.md (Revision 4)*
