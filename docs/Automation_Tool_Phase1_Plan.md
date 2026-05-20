# UFP Wood Treatment Project Automation Tool — "ProcessArc"
## Feature Design Plan — Phase 1
**Project:** ProcessArc — document automation application for UFP Industries SCADA wood treatment projects
**Scope of this document:** Design plan for the first two features only
**Author:** Texas Automation Systems / Randy
**Status:** Planning — no code
**Revision:** 5 — adds deployment recommendation (Section 16) and the standard-register / tank-configuration handling (Section 9A)

---

## 0. Build Scope and Direction

**This tool is being built UFP-specific first.** The Phase 1 build targets UFP Industries wood treatment projects only — UFP's document formats, UFP's naming conventions, UFP's standard interlock set. The configurable template and profile design (Sections 7 and 10) still applies, but the templates and the C&E profile shipped in Phase 1 are the UFP ones. A general, multi-customer version is explicitly not a Phase 1 goal. Building UFP-specific first keeps the scope bounded and gives us real answer keys to test against.

**P&ID-driven documentation is a planned future capability — designed for now, built later.** Beyond reading the sequence workbook, the longer-term goal is for the tool to also read P&ID drawings directly and generate documentation and a Cause & Effect matrix from the process depicted in them. This is not in Phase 1 scope, but it is a deliberate direction, so Phase 1 should be built without closing the door on it. See Section 15.

**Plant configuration varies between UFP plants — the tool must discover it, never assume it.** The number of cylinders, the number of mixing systems, the *numbering* of cylinders, and the *tank configuration* (which tanks exist, what chemical each holds, which cylinder each feeds) all differ from one UFP plant to the next. ProcessArc treats plant configuration as something it **reads from the input workbook at the start of every project**. Nothing in the tool is allowed to hard-code "two cylinders" or "Cylinder 1 and 2." See Section 2.3 and Section 6A.

**Deployment for Phase 1 is "run it locally as two processes" — not Docker, not a packaged executable yet.** Packaging is a distribution problem, and Phase 1 has no distribution problem (one user, one machine). See Section 16 for the full recommendation.

---

## 1. Background and Goal

Every UFP wood treatment SCADA project begins the same way: UFP hands over a graphics-and-sequence workbook (like `Fairless Hills Graphics and Sequence.xlsx` or `Hampton_Graphics_and_Sequence.xlsx`). From that, the integrator must produce a series of engineering deliverables by hand — most painfully the device tag list (`UFP_Ignition_FairlessHills.xlsx`) and the Cause & Effect matrix (the `C&E` sheet inside the commission workbook).

Today this is manual transcription work. It is slow, error-prone, and inconsistent between projects. The same valve gets named `Tnkv1` in one document, `TankV1` in another, and `Treat1_TankV1vlv_Out` in a third. Devices get missed. The Cause & Effect matrix gets rebuilt from scratch each time.

The goal is an application — **ProcessArc** — that ingests the UFP sequence workbook and auto-produces two standardized engineering documents:

1. **The device/IO list** — following the `UFP_Ignition_FairlessHills.xlsx` format, with every device discovered and listed, and with the standard repeating registers (tanks) pre-filled, leaving the PLC programmers only the registers that genuinely vary per plant.
2. **A draft Cause & Effect document** — following the `C&E` sheet format, pre-populated with standard interlocks and the discovered device columns.

These two features are the first to build and test. Everything else (P&ID ingestion, full commission workbook generation, etc.) comes later.

---

## 2. Design Principles Carried Into This Build

Three requirements shape the design and are stated up front because they affect almost every section.

### 2.1 The output format is a template, not a constant
The output format is the **UFP** format, but it will be *similar* project to project rather than always identical — sheet names may differ, columns may be added or dropped, a Control Valve sheet may be used on one site and empty on another, UDT folder paths may change.

Therefore the application treats the output format as **an input it reads**, not a layout it hard-codes. For each project, the engineer supplies a **template workbook**. The tool reads that template's structure and populates it with the discovered devices. The internal Device Model never changes; only the final rendering step adapts to the template in front of it.

The same principle applies to the Cause & Effect output: the legend block, column groupings, and the standard cause backbone become a **configurable profile**.

### 2.2 Device extraction uses the Claude API
The hardest stage is prose extraction — pulling device names out of running English sentences. Pattern matching against prose is brittle. The tool uses the **Claude API** for that stage. Sequence text goes to Claude with a structured-output prompt; a clean, classified device list comes back as JSON. Consequences are spelled out in Section 8.

### 2.3 Plant configuration is discovered, never assumed
**This is the most far-reaching principle.**

Comparing the two UFP examples we now have proves plant configuration is genuinely variable:

| Aspect | Fairless Hills | Hampton |
|--------|----------------|---------|
| Active cylinders | 2 | 2 |
| Cylinder numbers | 1, 2 | **1, 3** (Cylinder 2 exists but is idle/disconnected) |
| Mixing systems | 2 (separate ECO and MCA) | **1 unified** |
| Sequence sheets | 4 | 3 |
| Cross-cylinder naming | mostly consistent | **Cyl 1 uses P1/P2/S1; Cyl 3 uses VPD/VPS/VSS** |
| Tank configuration | 11 tanks, MCA + ECO split | 9 tanks, different chemical assignments |

The consequences for the design:
- **The tool must not assume two cylinders and two mixing systems.** It must count them from the input workbook.
- **The tool must not assume cylinders are numbered 1, 2, 3…** Hampton's are 1 and 3. The numbers come from the sheet names and the data, not from a counter.
- **The tool must not assume cylinders share device names.** Hampton's Cylinder 1 and Cylinder 3 name the same functions differently.
- **The four fixed C&E sequence-control columns (Treat 1/2 Pause, Mix 1/2 Pause) are wrong as a constant.** They must be generated from the discovered systems.
- **The tank configuration is per-plant.** Which tanks exist, what chemical each holds, and which cylinder each feeds all vary. This is read from the Chemical and Tank sheet. See Section 9A.

The mechanism is the **Plant Configuration step**, described in Section 6A.

---

## 3. What We Learned From the UFP Source Documents

The plan is grounded in real UFP files: the Fairless Hills set (three documents) and the Hampton sequence workbook (second example).

### 3.1 Input — the UFP sequence workbook
The **UFP-supplied source**. Sheet count varies (Fairless Hills 11, Hampton 10). Device information lives in:
- **Cylinder sequencing sheets** — prose step-by-step sequences naming valves, pumps, and sensors in running English. **The number of these sheets and their cylinder numbers vary by plant.**
- **Mix sequencing sheet(s)** — prose mix sequences. **There may be one unified mix sheet (Hampton) or several (Fairless Hills).**
- **Chemical and Tank** — structured tables: chemical properties, flow meter list, work tank inventory. The work tank table includes a "Cylinder Used" column tying tanks to cylinders, and (in Hampton) a "Cylinder Status" column marking idle cylinders. **This sheet is the authoritative source of the tank configuration (Section 9A).**
- **Graphic sheets** — embedded PNG images (used for human verification, not machine-parsed in Phase 1; see Section 15).

The critical insight remains: **device names live inside prose sentences**, not in clean columns. The Claude API handles that stage.

### 3.2 Output Template A — the UFP Ignition tag list
The **UFP device/IO list deliverable template** (`UFP_Ignition_FairlessHills.xlsx` is one example). 6 sheets, each a UDT type. The application produces this file with the device-identity columns filled, the standard repeating registers pre-filled (Section 9A), and the genuinely-variable registers left blank. Treated as one example of a UFP template — structure may vary slightly per project.

### 3.3 Output Template B — the UFP Cause & Effect sheet
The **UFP Cause & Effect deliverable template** (the `C&E` sheet inside the Fairless Hills commission workbook). A wide matrix: rows are causes, columns are device-output effects plus the sequence-control columns. Cells contain action codes (`P`, `C`, `O`, `E`, `D`, `A`, `SA`).

---

## 4. The Core Problem: Three Naming Conventions

This remains a central design challenge.

The same physical valve appears as:
| Document | Name |
|----------|------|
| Sequence workbook (UFP source) | `T1` or `Tnkv1` |
| Ignition tag list (`UFP_Ignition`) | `T1`, system `Cylinders`, number `1` |
| Cause & Effect sheet | `Treat1_T1vlv_Out` |

The application maintains a single **canonical device record** internally and renders it into whichever output format is being generated, using the configurable naming rules (Section 6.2).

**Hampton adds a wrinkle:** naming is not even consistent *between cylinders in the same plant*. Cylinder 1 uses `P1/P2/S1`; Cylinder 3 uses `VPD/VPS/VSS`. The naming rule engine renders names from each device's own base name and its own cylinder context — it never assumes one cylinder's names predict another's.

---

## 5. How the Application Should Work — High-Level Flow

The application runs as a pipeline. A user can stop, review, and correct between any two stages.

```
[0] CONFIGURE       Supply the UFP output template(s) + the UFP C&E profile
       |
[0A] DISCOVER       Read the workbook's sheets -> build the Plant Configuration
       |             (cylinders/mix systems, their numbers, idle ones, tank config)
       |
[1] INGEST          Read the UFP sequence workbook
       |
[2] EXTRACT         Send prose to the Claude API -> structured device list
       |             Read the Chemical/Tank tables directly
       |
[3] REVIEW          Human confirms Plant Configuration + corrects device list  (mandatory)
       |
[4] BUILD MODEL     Assemble the canonical Project Device Model
       |
[5] EXPORT          Render Feature 1 (IO list) and Feature 2 (C&E draft)
       |             into the supplied UFP templates, sized to the Plant Configuration,
       |             with standard registers pre-filled (Section 9A)
```

Before any device extraction, the tool determines the plant's actual configuration — cylinders, mixing systems, their numbers, idle ones, and the tank configuration. This drives everything downstream.

The Review stage (3) is mandatory and also covers confirming the Plant Configuration.

---

## 6A. Plant Configuration — Discovering the Shape of the Plant

This section describes how the tool handles plant variability.

### 6A.1 What the Plant Configuration Is
The Plant Configuration is a small, project-specific record the tool builds at Stage 0A, before extraction. It answers:
- **How many cylinders, and what are their numbers?** Read from cylinder sequencing sheet names.
- **How many mixing systems, and their numbers/names?** Read from mix sequencing sheet names.
- **Which cylinders or systems are idle?** Read from the Chemical and Tank sheet's status columns.
- **What is the tank configuration?** Which tanks exist, what chemical/preservative each holds, which cylinder each feeds, tank dimensions and volumes. Read from the Chemical and Tank sheet's work tank inventory table. This feeds Section 9A.

### 6A.2 How It Is Built
The tool inspects the workbook's sheet list and the Chemical and Tank tables:
1. Identify every cylinder sequencing sheet; extract the cylinder number from each name.
2. Identify every mix sequencing sheet; extract the mix system number/name from each.
3. Cross-check against the Chemical and Tank sheet — "Cylinder Used" and any status column — to catch idle cylinders that have data but no sequence sheet.
4. Read the full work tank inventory table — every tank, its chemical, its cylinder assignment, its dimensions.
5. Produce the Plant Configuration: cylinder systems (numbers + active/idle), mix systems, and the tank configuration.

### 6A.3 How It Is Used
Everything downstream is driven by the Plant Configuration, not by assumptions:
- **Extraction** processes exactly the sequence sheets the configuration found.
- **The Device Model** organizes devices under the actual system numbers.
- **The C&E column set** is generated from the configuration.
- **The cause library** scales to the configuration — including one tank-volume cause row per tank in the tank configuration.
- **Register pre-fill (Section 9A)** uses the tank configuration to decide how many tank instances exist and what each one is.

### 6A.4 Idle Systems
An idle cylinder (Hampton's Cylinder 2) is recorded as **present but idle**. By default it is excluded from extraction and both outputs, but shown to the engineer at review so the decision is explicit. The engineer can include it or leave it excluded.

### 6A.5 The Engineer Confirms It
The Plant Configuration — including the tank configuration — is presented at the start of the Review stage. The engineer confirms it before extraction results are built on top of it. A miscount here would corrupt both outputs, so it is checked first and explicitly.

---

## 6. The Project Device Model (the heart of the application)

Everything depends on a clean internal data structure. It is not code — it is the agreed-upon shape of the data. It is deliberately **independent of any template, of where a device was discovered, and of any assumed plant shape**.

### 6.1 A Device Record
| Attribute | Description | Example |
|-----------|-------------|---------|
| Canonical ID | Unique internal identifier | `CYL3_VALVE_VPD` |
| Device Class | Valve / Pump / VFD Pump / Control Valve / Tank | `Valve` |
| System | Cylinders or Mixing | `Cylinders` |
| System Number | The actual number from the Plant Configuration | `3` |
| Base Name | Short name as used in *this system's* sequence | `VPD` |
| Description | Human-readable function | `Pressure pump discharge valve` |
| Source Reference | Where it was found | `Cylinder 3 Sequencing, Raise Pressure` |
| Source Type | What kind of input produced it | `Sequence Prose` / `Table` *(future: `P&ID`)* |
| Confidence | How sure the extractor is | `High / Needs Review` |
| Ignition UDT Type | Which UDT it maps to | `Valves/Valve` |
| Ignition Folder | Tag folder path | `Edge/Valves` |
| C&E Output Tag | Rendered output tag name | `Treat3_VPDvlv_Out` |
| Register Values | Any registers ProcessArc pre-fills for this device | (see Section 9A) |
| Notes | Free text, carried to outputs | — |

Three attributes carry the lessons so far:
- **System Number** holds the *actual* number from the Plant Configuration — `3`, not a sequential index.
- **Source Type** is included now for the future P&ID extractor.
- **Register Values** holds whatever registers ProcessArc can pre-fill from a standard pattern (Section 9A). For most devices this is empty; for tanks it carries the standard tank register block. Genuinely-variable registers are never placed here.

### 6.2 Naming Rule Engine
A small, **configurable** set of rules converts a canonical device into each output's name, **using that device's own System Number and Base Name** — never an assumed value. For a Cylinder 3 valve named `VPD`:
- **Ignition tag list:** Name = `VPD`, System = `Cylinders`, System Number = `3`
- **C&E output tag:** `Treat{SystemNumber}_{BaseName}vlv_Out` → `Treat3_VPDvlv_Out`

Because the rules read each device's own number and name, they handle non-sequential numbering and cross-cylinder naming differences automatically.

### 6.3 Device Class Definitions
The five device classes map to the five UDT sheets. Which sheets exist and their exact headers come from the supplied template.

| Device Class | Maps To | Key Data Produced |
|--------------|---------|-------------------|
| Pump | Pump sheet | System, System Number, Name, Description |
| Valve | Valve sheet | System, System Number, Name, Description |
| VFD Pump | VFD Pump sheet | + speed/frequency identity |
| Control Valve | Control Valve sheet | + setpoint identity |
| Tank | Tank sheet | TankIn + TankOut identity + standard register block (Section 9A) |

---

## 7. Template Handling — How "Similar But Not Identical" Works

### 7.1 The Template Reader
Before generating, the tool reads the supplied UFP output template workbook and builds a **template map**: which sheets exist and their names, each sheet's header row, the position of metadata rows (`UDT Type:`, `Folder:`), and which columns are device-identity columns, which are standard-pattern register columns, and which are genuinely-variable register columns.

### 7.2 Column Matching
The tool matches Device Model attributes to template columns by header name, using a small alias dictionary. Columns are sorted into three kinds: device-identity columns (filled from the Device Model), standard-pattern registers (filled from the register pattern — Section 9A), and variable registers (left blank for the PLC programmers).

### 7.3 Graceful Behavior on Format Drift
- A template sheet the tool has no devices for is written empty (header preserved).
- A template column the tool doesn't produce is left blank, not dropped.
- A renamed template sheet is followed by name.
- A missing expected sheet triggers a warning at Stage 0.

### 7.4 The C&E Profile — Sized by the Plant Configuration
The C&E output is governed by a **C&E profile**. **The sequence-control columns are not fixed.** The profile defines the *pattern* — "one Treat column per active cylinder, one Mix column per mixing system" — and the actual columns are generated from the Plant Configuration. Fairless Hills yields Treat 1, Treat 2, Mix 1, Mix 2. Hampton yields Treat 1, Treat 3, Mix.

---

## 8. Claude API Integration — How Extraction Works

### 8.1 Where the API Is Used
The Claude API is used **only at the prose-extraction stage** (Stage 2, the cylinder and mix sequencing sheets). The structured Chemical and Tank tables are read directly. Plant Configuration discovery, template reading, the Device Model, review, and export do not call the API.

### 8.2 How the Extraction Call Works
For each sequencing sheet, the tool sends the sheet's text to the Claude API with a prompt that states the task (identify every field device), provides the device-class definitions and **the System and System Number for that specific sheet, taken from the Plant Configuration**, and requires a strict JSON response — one object per device.

### 8.3 What the API Changes — Be Explicit
- **Not fully offline.** The extraction stage needs network access; the rest of the pipeline runs offline.
- **The API key must be managed** — stored outside project files, never committed, never sent to the frontend.
- **UFP customer data leaves the building during extraction.** Only sequence prose is sent — not the whole workbook, not the graphics. Confirm this is acceptable per the UFP agreement.
- **Per-run cost and a failure mode.** API calls cost money and can fail. The tool must handle failures cleanly and never silently produce an empty device list.
- **Review matters more, not less.**

### 8.4 Pluggable Extractor Design
The extractor is a **pluggable component** behind a fixed interface. The Claude API sequence-prose extractor is the Phase 1 implementation. A future P&ID extractor (Section 15) becomes another implementation behind the same interface.

### 8.5 Cost and Volume Note
A handful of API calls per project, run once plus retries. Low-volume, low-cost.

---

## 9. Feature 1 — Auto-Populated IO / Device List

### 9.1 What It Produces
An Excel file matching **the supplied UFP template's** format. Every discovered device appears on the correct sheet with System, System Number, Name, Description, and Notes filled in, organized under the **actual cylinder/mix numbers from the Plant Configuration**. The **standard repeating registers are pre-filled** (Section 9A); only the genuinely-variable registers are left blank for the PLC programmers.

### 9.2 How It Works — Step by Step

**Step A — Load the template (Stage 0).** Read the supplied UFP IO-list template, build the template map, sort columns into device-identity / standard-register / variable-register.

**Step B — Discover the Plant Configuration (Stage 0A).** Inspect the workbook's sheets and tables; build the list of cylinders and mix systems with their actual numbers and idle status, and the full tank configuration (Section 6A).

**Step C — Ingest the sequence workbook.** Read all sheets. Separate prose sheets from table sheets.

**Step D — Extract devices from prose via the Claude API.** Process exactly the sequencing sheets the Plant Configuration found. Each sheet's devices are tagged with that sheet's true System Number.

**Step E — Extract devices from tables directly.** Read the Chemical and Tank sheet. Work tank inventory → Tank records; flow meter table → instrument records; chemical properties feed Tank descriptions.

**Step F — Classify and assign system context.** Each candidate gets a Device Class and is assigned to a system. Pressure and Strip pumps are classified as VFD Pumps where the sequence indicates VFD speed control.

**Step G — Apply standard register pre-fill (Section 9A).** For device classes with a known UFP standard register pattern — tanks in particular — populate each device's Register Values from the pattern. Variable registers are left empty.

**Step H — Present for review (Stage 3, mandatory).** First confirm the Plant Configuration. Then show the full device list, grouped by system and class, with confidence flags. The engineer renames, reclassifies, deletes false positives, adds missed devices, marks not-installed devices as excluded. Known cases: `V9` absent from prose but real; `MS1/MS3/MS5`, `NaNi` shown but not installed; an idle cylinder shown but not commissioned. The corrected list becomes the Project Device Model.

**Step I — Export into the template.** Apply the Ignition naming rules and write each device into the matching sheet/columns. Fill device-identity columns from the Device Model and standard-register columns from the Register Values. Leave variable-register columns blank. Preserve headers and metadata rows. Save as `{SiteName}_Ignition_IOList.xlsx`.

### 9.3 What "Done and Tested" Looks Like
Run on `Fairless Hills Graphics and Sequence.xlsx` with `UFP_Ignition_FairlessHills.xlsx` as the template. Success criteria:
- Every valve, pump, and tank in the real file is present, on the correct sheet, with correct System and System Number.
- The output matches the template's structure exactly.
- Standard tank registers are pre-filled correctly; variable registers are blank.
- Uncertain devices flagged in review, not dropped.
- Discrepancies (V9, MS valves) surfaced in review.
- **Second test — Hampton:** the tool discovers cylinders 1 and 3, one mix system, the Hampton tank configuration, and tags Cylinder 3 devices as System Number 3.
- **Third test:** a deliberately modified template — output follows the new template without code changes.

---

## 9A. Register Handling — What ProcessArc Fills and What It Leaves Blank

This section is new in Revision 5 and corrects the earlier blanket statement that ProcessArc leaves *all* registers blank.

### 9A.1 The Correction
ProcessArc does **not** leave every register blank. The reality is more precise:
- **Some registers follow a standard, repeating pattern that does not change between plants.** The clearest case is the **Tank UDT** — its register block (`TankIn.Density`, `TankIn.Diameter`, `TankIn.Length`, `TankIn.Minimum`, `TankIn.Pump`, `TankOut.Bits`, `TankOut.Volume`, `TankOut.Temp`, and so on) appears as a consistent, sequential `MW`-word block across UFP projects. Each tank instance occupies a fixed-size block, the next tank starting a fixed offset later.
- **What genuinely changes between plants is the tank *configuration*** — which tanks exist, what chemical/preservative each holds, which cylinder each feeds, and tank dimensions. This is data, read from the Chemical and Tank sheet, not register addresses.

So the rule is: **where a UFP standard register pattern exists, ProcessArc pre-fills it. Where registers genuinely vary per plant and per PLC wiring, ProcessArc leaves them blank.**

### 9A.2 The Standard Register Pattern
ProcessArc carries a **standard register pattern** as configurable data — part of the UFP profile, not buried in logic. For each device class that has one, the pattern describes:
- The starting `MW` word for the first instance.
- The set of register fields in the block and their offsets within it.
- The block size — how far apart consecutive instances start.

For tanks, this pattern lets ProcessArc compute the full register block for tank 1, tank 2, tank 3, … simply from the tank configuration's count and order. The Fairless Hills Ignition file's Tank sheet is the reference for this pattern.

### 9A.3 What Gets Pre-Filled vs. Left Blank

| Register kind | ProcessArc behavior | Example |
|---------------|---------------------|---------|
| Standard repeating pattern | **Pre-filled** from the pattern | Tank UDT register block — `MW1872`, `MW1874`, … per the offsets |
| Genuinely variable per plant / per PLC wiring | **Left blank** for the PLC programmers | Valve and pump `Manual` / `Outputs` coils, VFD setpoint/frequency words |
| Device-identity (not registers) | Filled from the Device Model | System, System Number, Name |

The result for the PLC programmers: the tank registers arrive done; they fill only what is truly wiring-specific.

### 9A.4 The Tank Configuration Itself
The tank configuration — distinct from the registers — is read from the Chemical and Tank sheet's work tank inventory:
- Which tanks exist (Fairless Hills 11, Hampton 9).
- What preservative/chemical each holds (Tank 1 MCA at Fairless Hills; Tank 1 ECO at Hampton).
- Which cylinder each tank feeds (the "Cylinder Used" column).
- Tank dimensions and min/max/target volumes.

This configuration populates the device-identity and description fields of each Tank record, and tells the register pre-fill how many tank blocks to generate. It is part of the Plant Configuration (Section 6A) and is confirmed by the engineer at review.

### 9A.5 Must Be Verified Before Use
The standard register pattern in Section 9A.2 is inferred from the Fairless Hills Ignition file's Tank sheet. **Before ProcessArc writes any register value, the engineer and the PLC team must confirm which register blocks UFP genuinely keeps constant across plants.** ProcessArc treats the pattern as configurable data precisely so it can be corrected without a code change. If in doubt for a given device class, the safe default is to leave its registers blank — pre-filling a wrong register is worse than leaving it empty. This is added to the Open Questions (Section 13).

---

## 10. Feature 2 — Draft Cause & Effect Document

### 10.1 What It Produces
An Excel sheet matching the **UFP C&E profile**: causes as rows, device outputs as columns, action codes in cells, **sized to the Plant Configuration**. It is a draft — pre-populated with everything determinable, judgment cells left for the human.

### 10.2 How It Works — Step by Step

**Step A — Build the column set from the Plant Configuration.** Generate one Treat sequence-control column per active cylinder and one Mix column per mixing system. Then add a column for every device with an output, rendered with its C&E output-tag name using its true System Number.

**Step B — Generate the standard cause rows, scaled to the plant.** The UFP cause library defines the cause *patterns*; the actual rows scale to the Plant Configuration and the IO list — one set of cylinder interlock rows per active cylinder, one e-stop row per e-stop, **one tank-volume row per tank in the tank configuration**.

**Step C — Pre-fill the obvious cells.** Apply the universal action rules: Emergency Stop → `P` on all sequence-control columns, `C` on every valve, pumps de-energized; a system-pause cause → `P` on its system column and `C` on that system's device columns; door interlocks → `P` on the affected cylinder; tank volume alarms → `P` on the systems using that tank.

**Step D — Leave judgment cells blank but marked.** Cause rows needing engineering judgment are flagged with an explanatory Note.

**Step E — Export into the C&E profile.** Write the matrix with the legend block, the Note/Cause/Alarm/Setpoint columns, and the generated effect columns. Save as `{SiteName}_CauseAndEffect_Draft.xlsx`.

### 10.3 What "Done and Tested" Looks Like
Run on the Fairless Hills device model with the UFP C&E profile, compare against the real `C&E` sheet. Success criteria:
- All standard cause rows present and scaled correctly.
- All device-output columns present with correct C&E tag names.
- Estop and system-pause rows fully and correctly pre-filled.
- Judgment cells clearly flagged, not guessed.
- **Second test — Hampton:** the generated C&E has Treat 1, Treat 3, and one Mix sequence-control column, cylinder interlock rows for cylinders 1 and 3, and tank-volume rows matching Hampton's tank configuration.

---

## 11. Why These Two Features First

- They share dependencies — the Plant Configuration and the Project Device Model. Build those once, both features consume them.
- They are verifiable. We have real UFP inputs and real UFP outputs to grade against, and two plants of differing shape to test variability.
- They deliver the highest manual-labor savings — the IO list and C&E are the most tedious documents to transcribe.
- They are bounded — neither requires P&ID image parsing or full commission-workbook generation.

---

## 12. Phase 1 Scope Boundaries

**In scope:**
- UFP-specific build only
- Loading a configurable UFP output template and UFP C&E profile
- Discovering the Plant Configuration (cylinder/mix-system count and numbering, tank configuration)
- Ingesting the UFP sequence workbook
- Claude API-based prose device extraction
- Direct table extraction (Chemical and Tank)
- The mandatory human review/correction step (including Plant Configuration confirmation)
- The Project Device Model
- Feature 1 — IO list export, with standard repeating registers (tanks) pre-filled
- Feature 2 — C&E draft export following the UFP profile, sized to the plant

**Explicitly out of scope for Phase 1:**
- Parsing P&ID images / drawings (planned future capability — see Section 15)
- Generating documentation and C&E directly from the process in a P&ID (see Section 15)
- A general, multi-customer version of the tool
- Generating the full commission workbook
- Auto-filling the genuinely-variable registers (valve/pump coils, VFD words — stays with the PLC programmers by design)
- Docker / packaged-executable distribution (deferred — see Section 16)
- Reverse direction (Ignition file → sequence doc)
- Multi-project database / project library (note: Hampton's "reference Moneta V1A programming" hints at future value here)

---

## 13. Open Questions to Resolve Before Building

1. **Naming rule coverage** — Catalog every output-tag pattern in the real UFP C&E (valves `..vlv_Out`, pumps `..pmp_Out`, conveyor VFDs `Treat1_Deck_VFD1_Out`) before locking the rule engine.
2. **Mix valve aliasing** — Sequence doc, Ignition file, and C&E diverge most on mix-system names. A confirmed alias table is needed.
3. **Device discrepancy handling** — Keep not-installed devices as excluded/greyed rows (recommended) or omit them?
4. **UFP cause library / profile ownership** — Who owns and versions the UFP C&E profile and cause library as more UFP sites are added?
5. **Confidence threshold** — Force everything into review in Phase 1 (recommended), tighten later.
6. **API key handling and data policy** — Where is the key stored; is sending UFP sequence prose to the Claude API confirmed acceptable per the UFP agreement?
7. **API failure and offline behavior** — Report and retry on failure; is an offline fallback extractor needed for Phase 1?
8. **Template library** — Where are UFP output templates stored, and how does the engineer pick one per project?
9. **Idle system handling** — When a cylinder is present but idle (Hampton's Cylinder 2), the default is to exclude it but show it at review. Confirmed?
10. **Plant Configuration confidence** — If a workbook's sheet naming is inconsistent, how does the tool flag a low-confidence Plant Configuration for extra review?
11. **Standard register pattern verification** *(new — Revision 5)* — The tank register pattern is inferred from the Fairless Hills Ignition file. Before ProcessArc writes any register, the PLC team must confirm which register blocks UFP keeps constant across plants. Which device classes besides Tank, if any, have a standard pattern? When in doubt, leave blank.

---

## 14. Suggested Build Order for Phase 1

1. Define and lock the Project Device Model structure (Section 6), including System Number, Source Type, and Register Values.
2. Build the **Plant Configuration discovery** (Section 6A) — count cylinders and mix systems, capture their real numbers, idle status, and the tank configuration.
3. Build the template reader and template map (Section 7), with the three-way column sort.
4. Build the sequence-workbook ingester (read all sheets).
5. Build the table extractor (Chemical and Tank).
6. Build the Claude API prose extractor behind the pluggable interface (Section 8.4).
7. Build the standard register pattern and the register pre-fill step (Section 9A) — after confirming the pattern with the PLC team.
8. Build the review interface — Plant Configuration confirmation first, then the device list.
9. Build Feature 1 export (IO list) — test against the real UFP Ignition file, then Hampton, then a modified template.
10. Build the UFP standard cause library and C&E profile, with plant-sized column generation.
11. Build Feature 2 export (C&E draft) — test against the real UFP C&E sheet, then Hampton.

Each step is independently testable. Steps 9 and 11 have real answer keys; the Hampton tests prove the plant-variability handling.

---

## 15. Future Capability — P&ID-Driven Documentation and Cause & Effect

This is **not Phase 1 work.** It is recorded here so Phase 1 is built in a way that does not block it.

### 15.1 The Goal
Beyond the sequence workbook, the tool should eventually read **P&ID drawings** directly and produce process documentation and a Cause & Effect matrix derived from the **process logic** in the drawing — equipment, instrumentation, interlock symbols, flow paths — not only from the written sequence.

A P&ID is a richer, more authoritative source than prose: it shows every instrument and line whether or not the sequence narrative mentions it. The Fairless Hills `V9` case proved this — `V9` was on the drawings but absent from the customer sequence prose.

### 15.2 Why Phase 1 Already Accommodates This
- **The Device Model is source-agnostic.** A device record carries a Source Type field.
- **The extractor is pluggable.** A future P&ID extractor becomes another implementation behind the same interface.
- **The Plant Configuration step is source-agnostic.** A future P&ID-based plant could have its configuration discovered from the drawing set instead of sheet names.

### 15.3 What a Future P&ID Phase Would Add (not now)
- An ingester for P&ID file formats (PDF, image, or CAD/vector).
- A P&ID extractor — likely vision-capable.
- Logic to merge a P&ID-sourced device list with a sequence-sourced one.
- A process-driven C&E generator.

### 15.4 Phase 1 Action Items to Protect This Path
- Keep the Source Type field in the Device Model from day one.
- Keep the Plant Configuration step independent of where the configuration was discovered.
- Do not let any prose-specific assumption leak past the extractor interface.
- When cataloging C&E patterns, note which interlocks are stated in prose versus only inferable from the process.

---

## 16. Deployment — Docker vs. Executable vs. Run Locally

This section is new in Revision 5 and answers the deployment question directly.

### 16.1 Recommendation for Phase 1: Run It Locally as Two Processes
While building and testing Phase 1, **do not package ProcessArc at all.** Run the backend and frontend directly — `python` for the FastAPI backend, the dev server for the React frontend. Both run on the engineer's machine; the browser opens the frontend at `localhost`.

The reasoning: Docker and a packaged executable both solve a *distribution* problem — getting the tool onto someone else's machine so it "just works." Phase 1 has no distribution problem. There is one user, on one machine, iterating quickly. Adding Docker now means rebuilding a container on every change; adding an executable now means a packaging step on every change. Both slow development for zero Phase 1 benefit.

### 16.2 When Packaging Is Needed: Executable, Not Docker
When ProcessArc is stable and should feel like a real installed application — a double-click icon, no terminal — the right choice is a **packaged executable**: Tauri or Electron wrapping the Python backend and the React frontend into one application. This fits what ProcessArc is: a local, single-user engineering tool.

**Docker** is the right choice only if ProcessArc later becomes a **shared service running on a server**. Given the decisions already made — local tool, customer documents stay on the machine, single user, API key local — that is not the expected direction. So:

| Option | Use it when | ProcessArc Phase 1 |
|--------|-------------|--------------------|
| Run locally as two processes | Building and testing, single user | **Yes — this is Phase 1** |
| Packaged executable (Tauri/Electron) | Tool is stable; engineers run it locally like an app | Later — likely future |
| Docker | Tool becomes a hosted/shared server service | Not expected; only if direction changes |

### 16.3 What This Means for the Build
Nothing about the architecture changes based on this. The Python-backend / React-frontend split (see the Technical Architecture document) is the same whether the tool is run as two processes, wrapped in an executable, or containerized. Packaging is a final wrapper applied to a finished tool — it is deliberately deferred so it does not slow Phase 1 development.

---

*Document prepared by: Texas Automation Systems / Randy*
*Phase 1 planning — design only, no implementation*
*Revision 5 — adds register handling / tank configuration (Section 9A) and the deployment recommendation (Section 16)*
