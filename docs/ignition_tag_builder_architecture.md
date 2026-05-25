# Ignition Tag Builder — Architecture

## What runs where

ProcessArc has two independent workflows reachable from the top-level
tab bar. **Project Wizard** processes UFP sequence workbooks into draft
IO list and C&E documents — the inputs to the PLC team's
Modbus-register fill-in step. **Ignition Tag Builder** processes the
populated Ignition tag-list template the PLC team returns, producing an
Ignition tag-instance JSON bundle. The two workflows share no runtime
state and no backend services; they are co-located in the same desktop
tool because the same engineer runs both.

## Overview

The Ignition Tag Builder is the second top-level ProcessArc workflow,
a peer of the Project Wizard. Unlike the wizard, it is:

* **Standalone**. It does not use the Project Device Model, it does
  not consult the review grid, and it is not a step in the
  Configure → Discover → Extract → Review → Export wizard.
* **Deterministic**. No LLM is involved. The transformation is a pure
  function of the input workbook.
* **A direct port of a Jython script** that runs inside Ignition
  Perspective. The Python port must produce JSON that is structurally
  identical to what `system.tag.configure(base_path, tag_config, "o")`
  would have written for the same workbook.

## Where the module lives

```
backend/features/ignition_tags/
├── __init__.py
├── schema.py        # pydantic models (with extra='forbid' on instances)
├── parser.py        # openpyxl-based workbook reader
├── builder.py       # nested-folder construction + instance assembly
├── packager.py      # zip of bundle + per-instance + manifest + report
├── router.py        # FastAPI routes; included from backend/api/main.py
└── README.md        # developer-facing run/debug notes
```

Tests:

```
backend/tests/test_ignition_tags.py
backend/tests/fixtures/ignition_tags/
├── golden_input.xlsx
├── golden_expected_bundle.json
└── README.md
```

The module is reachable in the FastAPI app as `POST /api/ignition-tags/build`,
wired into the app via `app.include_router(...)` in
[backend/api/main.py](../backend/api/main.py).

## Contract with the Excel template

The full workbook contract is in
[ignition_tag_template_spec.md](ignition_tag_template_spec.md). The
parser depends on every detail of that contract:

* Sheet 0 is the header sheet; Sheets 1..N are UDT data sheets.
* Data headers live at row index 0, columns A–D are reserved, the
  data table starts at column index 4.
* Three required headers (`Name`, `System Name`, `System Number`) plus
  arbitrary tag columns.
* Dot-notation in tag column headers expresses folder nesting.

## Contract with Ignition

See the **Prerequisites** section of
[ignition_tag_template_spec.md](ignition_tag_template_spec.md). The
short version: the gateway must already have the UDT type library
loaded. We generate instance configs only.

## Relationship to the other two features

None. The Ignition Tag Builder shares no code or state with the
existing IO List Generator and C&E Draft Generator. Specifically:

* It does **not** consume the Project Device Model.
* It does **not** touch the review grid.
* It does **not** depend on the Configure or Discover stages.
* It does **not** call Claude.

It can be used against any wood-treatment site, including ones that
have never been processed through the main ProcessArc pipeline.

## Data flow

```
xlsx upload
    │
    ▼
parser.parse_workbook(file_bytes)
    │   → ParsedWorkbook(provider, site, sheets[])
    │
    ▼
builder.build_all(parsed)
    │   → list[InstanceWithPath(base_path, instance_config)]
    │
    ▼
schema.InstanceConfig.model_validate(instance_config)   # extra='forbid'
    │
    ▼
packager.build_ignition_tree(instances)
    │   → single rooted folder tree, Ignition import format:
    │     { name: <site>, tagType: "Folder", tags: [<sys_name folder>, ...] }
    │
    ▼
HTTP 200 application/json
{
  "bundle":            { ... folder tree ... },         # the file the user downloads
  "validation_report": { errors:[], warnings:[...] },  # shown in the UI panel
  "site":              "...",            # used for the download filename
  "instance_count":    <int>             # UdtInstance leaf count
}
```

Errors collected during parse/build go into a `validation_report`
that is *always* returned — as a sibling field on a 200 (warnings
only — errors fail the request before this point), or as the body of
a 400.

The frontend writes only the `bundle` field to disk when the user
clicks Download JSON, so the downloaded file is a flat
Ignition-importable JSON object — no envelope wrapping in the file
itself.

## Faithfulness to the Jython reference

The reference Jython script lives in
[backend/features/ignition_tags/README.md](../backend/features/ignition_tags/README.md)
verbatim, so future maintainers can compare line-by-line. The
**golden test** in `backend/tests/test_ignition_tags.py` is the
contract test that proves the port matches: a known workbook is parsed
and built, and the output is compared key-for-key against a fixture
that captures what the Jython would have written.

Adding fields to the produced JSON to make it "more complete" will fail
that test. That is by design. The minimal four-key instance config is
what Ignition expects from `system.tag.configure`; everything else is
filled in from the UDT type definition at resolve time.

## Frontend

The two top-level features are reachable from a tab bar that lives
directly under the existing ProcessArc header band. Tabs:

* `Project Wizard` (default on app launch)
* `Ignition Tag Builder`

Both tab panels stay mounted simultaneously. The inactive panel uses
the HTML `hidden` attribute so its component tree (and React state)
survives a switch without an explicit state-snapshot layer. State
preserved across switches includes: the wizard's stage/inputs/draft
review edits, and the Tag Builder's last upload, results panels,
tree-expansion state, and held-in-memory zip blob.

Component layout:

```
frontend/src/
├── App.tsx                                 # tab shell only
├── components/
│   ├── TabBar.tsx                          # generic, label-driven tab bar
│   ├── ValidationReportPanel.tsx           # errors/warnings rendering
│   └── TagBundlePreview.tsx                # collapsible JSON tree
├── screens/
│   ├── WizardTab.tsx                       # the existing wizard, lifted
│   └── IgnitionTagBuilderTab.tsx           # Upload / Results / Error states
└── api/
    └── ignitionTags.ts                     # POST /api/ignition-tags/build
                                            # + JSZip-based zip parsing
```

Adding a third top-level workflow later is a single-entry addition to
the `TABS` array in `App.tsx` plus a new panel `<div>`; no `TabBar`
changes required.

The client posts multipart/form-data to `/api/ignition-tags/build`,
gets back either a 200 + JSON envelope or a 400 + structured validation
report. On success the client reads `bundle` and `validation_report`
out of the envelope to populate the preview; on download it serializes
just the `bundle` field to a `.json` file so the downloaded artifact
is a flat Ignition-importable JSON object with no envelope wrapping.

## Future work (deferred)

Listed here so they are not forgotten:

* **Direct gateway push** via the Ignition Web API (Phase 3d). Today
  the engineer downloads the zip and imports it by hand.
* **Per-instance `parameters` override.** The current Jython does not
  support per-instance `parameters.plc` overrides; neither does the
  port. If a future plant needs multiple PLCs in a single workbook, an
  optional `Parameter.<paramName>` column convention can be added.
* **UDT type generation.** Out of scope — types are imported into
  Ignition separately.
* **Search/filter on the JSON preview tree.** Useful when bundles get
  large; not needed for first-draft UFP workloads.
* **Persisting last-uploaded file across page refresh.** Out of scope;
  in-memory state only.
* **A landing screen / home tab as a third entry point.** Evaluated
  and rejected in favor of the two-tab layout.
