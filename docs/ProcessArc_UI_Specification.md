# ProcessArc — UI Specification
## Front-End Build Reference
**Project:** ProcessArc — UFP wood treatment project automation tool
**Scope of this document:** What the front end looks like and how to build it — the five screens, components, navigation, and visual style
**Author:** Texas Automation Systems / Randy
**Status:** UI design — no code
**Companion documents:** `Automation_Tool_Phase1_Plan.md` (Rev 5), `ProcessArc_Technical_Architecture.md` (Rev 2)

---

## 0. How This Document Relates to the Others

There are now three companion documents:
- **The Phase 1 Plan** says **what ProcessArc does** — the pipeline, the Plant Configuration, the Device Model, the two features.
- **The Technical Architecture** says **how ProcessArc is built** — Python backend, React frontend, the API boundary, the project layout.
- **This document** says **what the front end looks like and how to build it** — the screens, the components, the navigation, the visual style.

Read the plan and the architecture first. This document does not change either; it specifies the React frontend they describe. Every screen here maps to a pipeline stage defined in the plan.

---

## 1. The Shape of the Interface

ProcessArc is **not a free-form dashboard.** It is a pipeline with a fixed order: Configure → Discover → Extract → Review → Export. The interface must enforce that order, because skipping a stage — especially Review — would corrupt the output.

Therefore the frontend is a **stepped wizard**: five screens, traversed left to right, sharing one frame. A persistent step bar across the top shows where the engineer is and what is done. The engineer cannot jump ahead past an incomplete stage; they can go back to revisit a completed one.

```
┌──────────────────────────────────────────────────────────┐
│  ProcessArc            — {Project Name}    {source file}  │   Header
├──────────────────────────────────────────────────────────┤
│  [1 Configure] [2 Discover] [3 Extract] [4 Review] [5 ...] │   Step bar
├──────────────────────────────────────────────────────────┤
│                                                            │
│                  ACTIVE SCREEN CONTENT                     │   Screen body
│                                                            │
├──────────────────────────────────────────────────────────┤
│  [< Back]                              [Continue >]        │   Footer nav
└──────────────────────────────────────────────────────────┘
```

The header, step bar, and footer navigation are persistent. Only the screen body changes between stages.

---

## 2. The Five Screens

### 2.1 Screen 1 — Configure
**Pipeline stage:** Stage 0 (Plan §5)
**Purpose:** The engineer supplies the three input files for the project.

**Contents:**
- Three upload slots, side by side:
  1. **Sequence workbook** — the UFP-supplied graphics-and-sequence Excel file (required).
  2. **UFP IO template** — the Ignition tag-list template to render Feature 1 into (required).
  3. **C&E profile** — the Cause & Effect profile (optional; a default UFP profile is used if none is supplied).
- Each slot is a file-drop / browse target. Once a file is chosen, the slot shows the filename and a confirmation check.
- A project name field (defaults to the sequence workbook's site name).

**What the engineer can do:** Browse for and attach each file. Clear and re-pick a file.

**What it sends to the backend:** On Continue, uploads the attached files (Architecture §8, "Upload project files"). The backend then runs Stages 0, 0A, 1, 2.

**Continue is enabled when:** the two required files are attached.

---

### 2.2 Screen 2 — Discover (Confirm Plant Configuration)
**Pipeline stage:** Stage 0A (Plan §6A)
**Purpose:** Show the engineer the plant configuration ProcessArc discovered from the workbook, for confirmation before extraction results are trusted.

**Contents:**
- A short line of explanation: "ProcessArc found this from the workbook. Confirm before continuing."
- A small grid of configuration cards, each a discovered fact:
  - **Cylinders** — the active cylinder numbers and any idle ones (e.g. "1, 3 active · 2 idle").
  - **Mixing systems** — count and description (e.g. "1 unified").
  - **Tanks** — count and breakdown (e.g. "9 — 3 work, 6 supply").
  - **Sequence sheets** — how many were found.
- Idle systems are clearly labelled as idle and excluded by default.

**What the engineer can do:** Read the discovered configuration. Confirm it is correct. If something is wrong (a miscount, an idle cylinder that should be included), the engineer can correct it here before continuing — this is the system-level equivalent of the device review on Screen 4.

**What it sends to the backend:** On confirm, the confirmed Plant Configuration (Architecture §8, "Submit confirmed config").

**Continue is enabled when:** the engineer has confirmed the configuration.

**Why this screen exists on its own:** A miscount of cylinders or mixing systems would corrupt both deliverables. Per Plan §6A.5, the configuration is checked first and explicitly, before anything is built on it.

---

### 2.3 Screen 3 — Extract (Progress)
**Pipeline stage:** Stage 2 (Plan §5, §8)
**Purpose:** Show extraction progress so the engineer can see what is happening and catch failures.

**Contents:**
- A checklist of extraction tasks, each with a live status (done / running / queued / failed):
  - Table extraction — "Tables read directly — N tanks, N flow meters" (this is the no-API, direct read).
  - One row per sequence sheet — "Cylinder 1 sequence — sent to Claude API", etc.
- A progress bar showing overall completion.
- If an API call fails, the failed row shows a clear error state and a retry control — never a silent empty result (Plan §8.3, Architecture §9.2).

**What the engineer can do:** Watch progress. Retry a failed extraction. This screen is mostly passive — the engineer waits.

**What it sends to the backend:** Nothing during the screen; on completion it advances automatically to Review. A retry re-triggers the failed extraction.

**Design note — the data boundary is visible here.** The checklist deliberately distinguishes "tables read directly" (local, no API) from "sequence sent to Claude API" (the only step that leaves the machine). This makes the data boundary from Plan §8.3 visible to the engineer.

---

### 2.4 Screen 4 — Review (Device Grid) — THE KEY SCREEN
**Pipeline stage:** Stage 3 (Plan §5, §9.2 Step H)
**Purpose:** The mandatory human checkpoint. The engineer confirms, corrects, adds, and excludes devices before the outputs are generated.

This is the most important and most interactive screen in ProcessArc. It is where the value of the human-in-the-loop design is realized.

**Contents:**
- A confirmation banner at the top restating the confirmed Plant Configuration (e.g. "Cylinders 1, 3 active · Cylinder 2 idle, excluded · 1 mixing system · 9 tanks").
- A summary line: total device count and how many need review (e.g. "47 devices · 3 need review").
- Filter chips: All systems, one chip per system (Cylinder 1, Cylinder 3, Mixing), and a "Needs review" filter.
- **The device grid** — one row per device, with columns:
  - **Device** — the device name (editable — see §3.3).
  - **Class** — Valve / Pump / VFD Pump / Control Valve / Tank (editable dropdown).
  - **System** — which cylinder or mixing system, with the true number.
  - **Description** — human-readable function (editable).
  - **Status** — Confirmed / Low confidence (flagged) / Excluded.
- Rows needing review are visually highlighted (warning background).
- Action buttons: Add device, Edit selected.

**What the engineer can do:**
- **Confirm** a device (accept it as-is).
- **Edit** a device — rename it, change its class, change its description (see §3.3 on naming).
- **Exclude** a device — mark a not-installed device so it stays out of the outputs (e.g. `NaNi`, `MS1/MS3/MS5`).
- **Add** a device the extractor missed (e.g. `V9`, absent from the prose but real).
- **Filter** the grid by system or by "needs review" to focus.

**What it sends to the backend:** On Continue, the corrected device list — every confirmation, edit, exclusion, and addition (Architecture §8, "Submit confirmed config + corrections"). This becomes the Project Device Model.

**Continue is enabled when:** every flagged (low-confidence) device has been either confirmed, edited, or excluded — nothing ambiguous is left unresolved.

**Known cases this screen must handle (from the plan):**
- `V9` — absent from the customer prose but real; the engineer adds it.
- `MS1/MS3/MS5`, `NaNi` — shown but not installed; the engineer excludes them.
- An idle cylinder's devices — shown but not commissioned; confirmed excluded.
- A device whose name differs from the plant standard — the engineer renames it (see §3.3).

---

### 2.5 Screen 5 — Export (Download)
**Pipeline stage:** Stage 5 (Plan §5, §9, §10)
**Purpose:** Generate and hand over the two deliverables.

**Contents:**
- Two result cards, side by side:
  1. **IO / device list** — filename (e.g. `Hampton_Ignition_IOList.xlsx`), a one-line note ("tank registers pre-filled"), and a Download button.
  2. **Cause & Effect draft** — filename (e.g. `Hampton_CauseAndEffect_Draft.xlsx`), a one-line note ("Treat 1, 3 + Mix"), and a Download button.
- Each note reflects what the plan promises: the IO list has standard tank registers pre-filled (Plan §9A); the C&E is sized to the discovered plant (Plan §10).

**What the engineer can do:** Download each file. Optionally go back to Review to make a correction and re-export.

**What it sends to the backend:** On entry, triggers the export (Architecture §8, "Run export"). Download requests fetch the finished files.

---

## 3. Component Breakdown

The React frontend is built from a small set of reusable components. Named by purpose, not final code names.

### 3.1 Frame Components (persistent across all screens)
| Component | Responsibility |
|-----------|---------------|
| App Shell | Holds the header, step bar, screen body, and footer; owns which step is active |
| Header | Shows the ProcessArc name, the project name, and the source filename |
| Step Bar | The five-step indicator; shows done / active / upcoming; enforces no-skip |
| Footer Nav | Back and Continue buttons; Continue is enabled/disabled per the active screen's rule |

### 3.2 Screen Components (one per screen)
| Component | Screen | Responsibility |
|-----------|--------|---------------|
| Configure Screen | 1 | Three upload slots + project name field |
| Discover Screen | 2 | Plant Configuration cards + confirm |
| Extract Screen | 3 | Extraction checklist + progress bar + retry |
| Review Screen | 4 | The device grid + filters + add/edit/exclude |
| Export Screen | 5 | Two result cards + download buttons |

### 3.3 Shared / Detail Components
| Component | Used by | Responsibility |
|-----------|---------|---------------|
| Upload Slot | Configure | One file-drop / browse target with filename + confirmation state |
| Config Card | Discover | One discovered fact (cylinders, tanks, etc.) |
| Progress Row | Extract | One extraction task with a live status |
| Device Grid | Review | The interactive table of devices |
| Device Row | Review | One device — displays its fields, supports inline edit |
| Device Edit Form | Review | The form to rename / reclassify / re-describe a device, or add a new one |
| Filter Chips | Review | The system and "needs review" filters |
| Result Card | Export | One deliverable with its filename, note, and download button |
| Status Badge | Review, Extract | A small coloured label — Confirmed / Low confidence / Excluded / Running / Failed |

### 3.4 The Device Edit Form — Naming
The Device Edit Form is where the engineer can rename a valve or pump. Per the plan's naming design, a device name is **not locked once extracted** — it is an editable field. A name the engineer changes is carried into both outputs (the IO list and the C&E) through the naming rule engine. The form lets the engineer set the device's name, class, and description, and is also used (with empty fields) to add a device the extractor missed.

---

## 4. Wizard Navigation Rules

The step bar and footer enforce the pipeline order.

| Rule | Behavior |
|------|----------|
| No skipping ahead | The engineer cannot click a future step that is past the current incomplete one |
| Going back is allowed | The engineer can return to any completed step to revisit or correct |
| Continue is gated | Each screen defines when Continue is enabled (see each screen above) |
| Review cannot be bypassed | There is no path from Extract directly to Export — Review (Screen 4) is always traversed |
| Re-export after a correction | From Export, the engineer may go back to Review, change something, and re-export |

The "Review cannot be bypassed" rule is the UI expression of the plan's mandatory human checkpoint (Plan §5, Architecture §9.4). The wizard structure makes it structurally impossible to skip.

---

## 5. Visual Style

ProcessArc is an internal engineering tool. The visual style is **clean, flat, and functional** — clarity over decoration.

| Aspect | Specification |
|--------|--------------|
| Layout | Single centered frame; persistent header, step bar, footer; one screen body at a time |
| Surfaces | White / light cards on a neutral background; thin 0.5px borders; rounded corners |
| Color use | Mostly neutral. Color carries meaning only: blue = the active step / primary action, green = confirmed / done, amber = needs review / low confidence, grey = excluded / inactive, red = failure |
| Typography | One sans-serif family; two weights (regular and medium); sentence case everywhere; device names in a monospace font so tags like `V9` and `Treat3_VPDvlv_Out` read clearly |
| Density | The device grid is compact — many rows visible at once. The other screens are airier |
| Icons | Simple outline icons, one per concept (upload, check, flag, download). No decoration |
| Status badges | Small coloured labels using the meaning-colors above |
| No | No gradients, no drop shadows, no animation beyond simple progress indication, no dark decorative surfaces |

The wireframes rendered during planning are the visual reference for this style. They are low-fidelity — layout and flow, not pixel-final design — but the structure, the step bar, the device grid, and the color-for-meaning approach are as specified here.

### 5.1 The Step Bar — Visual States
| State | Appearance |
|-------|-----------|
| Done | Neutral surface, a green check |
| Active | Highlighted with a blue 2px border and blue label — the "you are here" step |
| Upcoming | Plain, muted label, no fill |

### 5.2 The Device Grid — Row States
| Row state | Appearance |
|-----------|-----------|
| Confirmed | Normal background, green "Confirmed" badge |
| Needs review | Amber/warning background, amber "Low confidence" badge with a flag icon |
| Excluded | Normal background, grey "Excluded" badge with a struck-through / eye-off icon |

---

## 6. What the Frontend Does Not Do

Restating the boundary from the Technical Architecture, because it shapes the UI:
- The frontend **never reads or writes Excel files** — it uploads them to the backend and downloads results.
- The frontend **never calls the Claude API** — only the backend does (Architecture §2.3).
- The frontend **never holds the API key.**
- The frontend **holds no business logic** — no extraction, no naming rules, no register pre-fill. It presents screens, collects the engineer's input, and sends it to the backend.

The frontend is the engineer's window into the pipeline. All work happens in the Python backend.

---

## 7. Suggested Build Order (Frontend)

Complements the architecture's build order (Architecture §10), viewed through the UI.

1. **App Shell + Step Bar + Footer Nav** — the frame, with placeholder screen bodies. Get the wizard navigation working first.
2. **Configure Screen** — upload slots; confirm files reach the backend.
3. **Extract Screen** — the progress checklist; confirm it reflects backend status.
4. **Discover Screen** — the Plant Configuration cards and confirm.
5. **Review Screen** — the device grid, then inline edit, then add/exclude. This is the largest piece; build it in that order.
6. **Export Screen** — result cards and downloads.

Build the frame first, then the simple screens (Configure, Extract, Discover), then the Review grid last because it is the most complex. The Export screen is quick once the backend produces files.

---

*Document prepared by: Texas Automation Systems / Randy*
*ProcessArc UI specification — design only, no implementation*
*Companion to Automation_Tool_Phase1_Plan.md (Rev 5) and ProcessArc_Technical_Architecture.md (Rev 2)*
