# ProcessArc — Build Status

**Companion to:** `Automation_Tool_Phase1_Plan.md` (Rev 5) · `ProcessArc_Technical_Architecture.md` (Rev 2) · `ProcessArc_UI_Specification.md`
**Purpose:** A current as-built reference. The three design docs above were written before the build and are preserved unchanged; this document tracks what's actually been built, where it diverged from the plan, and what's outstanding.
**Maintenance:** Update this file when the codebase changes. The design docs are historical and should not be retroactively edited.

---

## 1. Build state at a glance

| Plan section | Component | State |
|---|---|---|
| §5 Stage 0 | Configure — upload screen + project create endpoint | **Built** |
| §6A | Plant Configuration Discovery | **Built** |
| §5 Stage 1 | Workbook Ingester | **Built** |
| §9.2 Step E | Table Extractor (Chemical & Tank) | **Built** |
| §8 / §8.4 | Pluggable Prose Extractor — `ClaudeProseExtractor` | **Built**; validated offline. Not yet run against real UFP prose — gated on Open Q6. |
| §8 (extra) | `DryRunProseExtractor` — no-network synthetic extractor | **Built**; for UI work and Q6-pending use |
| §5 Stage 2 | Extract pipeline + endpoint + Extract screen | **Built**; per-task retry, orphaned-run self-heal on restart |
| §6 | Project Device Model | **Built** |
| §6.2 | Naming Rule Engine | **Built** |
| §7 | Template Reader / Template Map | **Built** |
| §9 | Feature 1 — IO List Exporter | **Built**; standard tank registers pre-filled (§9A) |
| §9A | Standard register pattern (tanks) | **Built**; inferred from Fairless Hills — pending PLC verification (Open Q11) |
| §10 / §7.4 | Cause Library + C&E Profile + C&E Exporter | **Built**; sized to Plant Configuration |
| Extra | Treating Sequence `.docx` exporter (Tier 1 + Tier 2) | **Built**; line classifier with marked typo cleanup |
| §5 Stage 3 | Review screen + device-model endpoint | **Built**; inline edit, add, exclude, "Needs review" filter |
| §5 Stage 5 | Export screen + endpoints | **Built**; three result cards (IO list, C&E, Sequence doc) |
| §8.3 / UI §1 | Settings UI for API key management | **Built**; masked display, header status dot, validates `sk-ant-` prefix |
| §15 | P&ID extractor | **Out of scope (Phase 2)**; Source Type field reserved |
| §12 | Docker / packaged executable | **Out of scope (Phase 1)**; runs locally as two processes |

All five wizard screens are built and the end-to-end pipeline runs against the real Fairless Hills workbook.

---

## 2. Modules — quick reference

### Backend

| Path | Purpose |
|---|---|
| `backend/api/main.py` | FastAPI app, CORS, `/health`, router wiring |
| `backend/api/store.py` | In-memory + on-disk per-project store (`projects/{id}/state.json`) |
| `backend/api/routers/projects.py` | Create project, get/confirm Plant Configuration, get/save Device Model |
| `backend/api/routers/extract.py` | Start / poll / retry extraction; per-project concurrency lock; orphaned-RUNNING self-heal |
| `backend/api/routers/export.py` | POST renders all three deliverables; GETs serve them |
| `backend/api/routers/settings.py` | API-key CRUD via the Settings UI |
| `backend/config/discover.py` | Plant Configuration discovery (cylinders, mix systems, tanks, idle flags) |
| `backend/ingest/workbook.py` | Open `.xlsx`, classify every sheet, expose `text_lines()` |
| `backend/extract/tables.py` | Header-driven extractor for the Chemical & Tank sheet |
| `backend/extract/prose.py` | Pluggable `ProseExtractor` ABC + `ClaudeProseExtractor` (Plan §8) |
| `backend/extract/dry_run.py` | `DryRunProseExtractor` — deterministic devices, no API call |
| `backend/extract/pipeline.py` | Per-task orchestration of Stage 2; merges results into the Device Model |
| `backend/model/device.py` | `DeviceRecord`, `DeviceModel`, the five `DeviceClass` values, `Confidence`, `ReviewStatus`, `SourceType` |
| `backend/model/plant.py` | `PlantConfiguration`, `CylinderSystem`, `MixSystem`, `TankRecord` |
| `backend/model/project.py` | `ProjectState`, `ExtractState`, `ExtractTask`, `PipelineStage` |
| `backend/naming/__init__.py` | `ignition_name()` + `ce_output_tag()` — canonical → output names |
| `backend/profiles/ufp_ce.py` | UFP cause library: estop, system pause, field e-stops, OverPSI, door interlocks, tank-volume rows |
| `backend/profiles/ufp_registers.py` | Standard tank register pattern (TankIn 14-word, TankOut 8-word blocks) |
| `backend/export/template.py` | Read UFP IO-list template; classify columns identity / standard / variable |
| `backend/export/io_list.py` | Render Device Model into the template |
| `backend/export/ce.py` | Render the C&E draft (three tabs: C&E, Treat Sign Off, Mix Sign Off) |
| `backend/export/sequence_doc.py` | Treating Sequence `.docx` — structured per-step rendering |
| `backend/export/sequence_classify.py` | Deterministic line classifier supporting `sequence_doc.py` |
| `backend/settings/config.py` | pydantic-settings; `.env` ahead of OS env; `reload_settings()`; `upsert_env_var()` |

### Frontend

| Path | Purpose |
|---|---|
| `frontend/src/App.tsx` | App Shell, wizard routing, stage state |
| `frontend/src/screens/ConfigureScreen.tsx` | Stage 0 — three upload slots, project name |
| `frontend/src/screens/DiscoverScreen.tsx` | Stage 0A — Plant Configuration confirmation cards |
| `frontend/src/screens/ExtractScreen.tsx` | Stage 2 — per-sheet progress with retry; data-boundary visible per UI §2.3 |
| `frontend/src/screens/ReviewScreen.tsx` | Stage 3 — device grid, inline edit, add modal, exclude |
| `frontend/src/screens/ExportScreen.tsx` | Stage 5 — three result cards + downloads |
| `frontend/src/components/ApiKeySettings.tsx` | Settings UI for the Anthropic key |
| `frontend/src/components/Header.tsx`, `StepBar.tsx`, `FooterNav.tsx` | Persistent frame |
| `frontend/src/api/client.ts`, `types.ts` | Typed API client mirroring backend models |
| `frontend/src/lib/theme.ts` | Dark-mode hook (localStorage + `prefers-color-scheme`) |
| `frontend/src/lib/demoPlant.ts` | Fairless Hills stand-in for `?demo=discover` |

---

## 3. Where the build diverged from the plan (worth knowing)

These are deliberate, not regrettable — but they aren't in the Plan/Architecture/UI Spec because they came up during the build.

- **A third exported deliverable: a Treating Sequence Word document** (`sequence_doc.py` + `sequence_classify.py`). The Plan describes two deliverables (IO list + C&E). The Word doc was added during the build as a customer-facing companion. It reads the workbook directly and renders the prose as a structured numbered-step document with a cover, TOC, transition callouts, conditional nesting, customer-note callouts, marked typo cleanup with an Editorial Notes trail, and (Tier 2) a per-step device summary strip when a Device Model is supplied.
- **A `DryRunProseExtractor` alongside the Claude one.** Behind the same `ProseExtractor` interface. Exists so the Extract screen can be exercised end-to-end without a key or network — and as a safe default while UFP data-policy sign-off (Open Q6) is still open. Invoked with `?dry_run=true` on the extract POST.
- **Per-task extraction with per-task retry.** The Plan describes Stage 2 as a single extraction step. In the build, each sequencing sheet is its own task with its own retry path. A failure on one sheet does not cascade; the others continue. Stage advances to Review iff at least one task succeeded.
- **Orphaned-RUNNING self-heal.** If uvicorn restarts mid-extraction, persisted RUNNING tasks would otherwise leave the UI spinning forever. On the next GET, the extract router marks them FAILED with a clear note ("Server restarted mid-run. Retry to continue."). Engineer-recoverable.
- **The Device Model PUT auto-promotes HIGH-confidence PENDING devices to CONFIRMED on save.** Per Open Q5's Phase 1 default ("review everything but don't force a click on HIGH"). NEEDS_REVIEW devices still require an explicit click.
- **`.env` is ordered ahead of OS env vars in pydantic-settings.** A stale exported `ANTHROPIC_API_KEY` from another app cannot shadow the UI-saved key. Documented in `settings/config.py`.
- **C&E export has three tabs**, not one — the `C&E` matrix plus `Treat Sign Off` and `Mix Sign Off` sheets. Sign-off lives in the Excel deliverable rather than on the wizard.
- **Frontend dark mode.** Not in the UI Spec. Toggleable in the header, persisted to localStorage, respects `prefers-color-scheme`.

---

## 4. Test coverage

| File | Scope |
|---|---|
| `backend/tests/test_prose_extractor.py` | `ClaudeProseExtractor` — interface conformance, §8.2 system-context stamping, §8.3 failure contract (every failure raises; never a silent empty list), empty-sheet handling, defensive parsing (fences, unknown class, duplicates, missing base_name), prompt construction |
| `backend/tests/test_extract_pipeline.py` | `run_extract` / `retry_task` — happy path, one-sheet-fails-others-succeed, all-fail stays on EXTRACT, table-failure isolation, retry recovery, no-double-add on retry, store updated during run (not only at end) |
| `backend/tests/test_review_endpoint.py` | `GET`/`PUT /projects/{id}/device-model` — empty model on no extract, replace semantics, Continue gate (advances iff every NEEDS_REVIEW resolved), HIGH PENDING auto-promote, NEEDS_REVIEW PENDING never auto-promoted |
| `backend/tests/smoke_fairless.py` | Smoke script against the real Fairless Hills workbook; asserts headline facts (2 cylinders, ECO + MCA mix, 11 tanks, Tank 4 idle) |

Run from the project root: `pytest` (uses `pytest.ini` for asyncio config) and `python -m backend.tests.smoke_fairless`.

**Untested:** `sequence_classify.py` and `sequence_doc.py` (the newest modules). The classifier is heuristic and has a closed set of input shapes — it would pay back on a small test file as more plants are added.

---

## 5. Open items (from Plan §13, plus build-time additions)

Tracked here because their status changes as the project moves; the Plan's §13 lists are historical.

- **Open Q6 — UFP data-policy sign-off** for sending UFP sequence prose to the Claude API. **Status: open.** The Prose Extractor module is built and offline-validated; until Q6 is signed off, run the Extract stage with `?dry_run=true`. Worth checking whether the Anthropic API tier in use has zero-data-retention as part of the sign-off conversation.
- **Open Q11 — standard register pattern verification.** The tank register pattern in `profiles/ufp_registers.py` is inferred from the Fairless Hills Ignition file. Other device classes are intentionally left blank. PLC team confirmation pending.
- **Open Q4 — C&E profile / cause library ownership.** Currently `profiles/ufp_ce.py` hardcodes the generators. The data shape is simple enough to externalize when ownership/versioning is decided.
- **Open Q1 — naming rule catalog completeness.** `naming/__init__.py` implements the patterns visible in current UFP docs and flags unknown classes with `<<UNKNOWN_CLASS:…>>` in the exported tag rather than silently guessing.
- **Open Q8 — template library / engineer template picker.** Templates live in `templates/` per Architecture §7. Per-project template selection on the Configure screen is not built; the engineer uploads the template each time.
- **ERP plant number for Fairless Hills.** Three numbers (552 / 554 / Moneta-554-comment) have appeared across builds. The Sequence doc cover prints `PlantConfiguration.erp_number` — worth confirming on the Discover screen before shipping a doc externally.
- **`CLAUDE_MODEL` in `.env.example` is `claude-sonnet-4-6`.** Anthropic API model identifiers are dated (e.g. `claude-sonnet-4-6-20251022` shape). Confirm the exact valid model string before the first real API call, or the call will fail with a confusing "model not found" error. Engineer to handle per prior agreement.
- **Q5 confidence threshold default** — Phase 1 review-everything is in place via the auto-promote rule (see §3 above). Worth tightening once review patterns are clear.

---

## 6. Known small things, recorded so they're not lost

These are not bugs and not blocking. They are the kind of thing that gets forgotten between sessions.

- **`ProjectState.extraction_log: list[dict]`** is defined but never written to. Either start logging extract events to it or remove the field.
- **`ProjectState.errors: list[str]`** is written by `projects.py` on discovery failure but never rendered in the frontend. The 400 response already carries the detail; the persisted field is redundant unless surfaced.
- **`backend/api/main.py` and `backend/api/routers/projects.py` use 4-space indentation.** The rest of the project uses tabs. Worth normalising for consistency.
- **`smoke_fairless.py` has a hardcoded absolute path** (`/Users/randylesovsky/Documents/project_manager/Fairless Hills Graphics and Sequence.xlsx`). Works on the build machine; fails anywhere else.
- **`ClaudeProseExtractor` catches every exception as a generic `ProseExtractionError`.** Anthropic's SDK exposes typed errors (`AuthenticationError`, `RateLimitError`, `APIConnectionError`, `APITimeoutError`). Catching them separately would let the Extract screen surface actionable messages ("check your key" vs. "rate limited, wait" vs. "network").
- **No `timeout=` on the API call.** A hung connection would leave a task RUNNING indefinitely; the orphaned-RUNNING self-heal only fires on server restart.
- **The Word-doc `_devices_referenced_in_step` heuristic in Tier 2** matches device base_names by case-insensitive word boundary. Robust on the Fairless Hills corpus; bears watching as more plants land with short base names.
- **No projects-list endpoint or project picker.** A project is reachable only by its 12-char hex id; resuming work between sessions requires the id from disk.

---

## 7. Hardware / environment

The build and test environment is:

- macOS, Python 3.10+, Node 18+
- Backend dependencies pinned in `backend/requirements.txt` (FastAPI 0.115.4, pydantic 2.9.2, openpyxl 3.1.5, python-docx >=1.1,<2.0, anthropic >=0.45,<1.0)
- Frontend on React 19, Vite, TypeScript, Tailwind 3 (full version list in `frontend/package.json`)

No Docker, no packaged executable, no hosted server. Per Plan §16, packaging is deferred until the tool is stable.

---

*Last updated when the code last changed. If this file disagrees with the code, the code is right and this file needs a refresh.*
