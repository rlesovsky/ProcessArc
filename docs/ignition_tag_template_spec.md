# Ignition Tag Builder — Excel Template Specification

This document is the contract between the user-supplied `.xlsx` template
and the ProcessArc Ignition Tag Builder. A PLC programmer who has never
seen ProcessArc should be able to read this and fill out a template
correctly without further help.

The builder is deterministic: same workbook in → same JSON out. It is a
direct port of an existing Ignition Perspective Jython script that has
been running in production. Behavior matches that script exactly.

---

## Workbook layout at a glance

```
+---------------------- Sheet 0 (header) -----------------------+
|   A    B               C                D   E   F   G ...    |
| 1                                                             |
| 2 ...  Tag Provider:   <tag provider>   ...  <-- value in C2  |
| 3 ...  Site Name:      <site name>      ...  <-- value in C3  |
+---------------------------------------------------------------+

+--------------------- Sheet 1..N (data) -----------------------+
|   A    B           C                D   E              F  ... |
| 1                                                             |
| 2 ...  UDT Type:   <UDT type id>    ...  <-- value in C2      |
| 3 ...  Folder:     <folder name>    ...  <-- value in C3      |
| 4 ...                                                         |
| 5                  (blank cols A-D)  System Name  System ...  | <- header row
| 6                  (blank cols A-D)  Mixing       2       ... | <- data row
| 7                  (blank cols A-D)  Mixing       1       ... |
| 8                                                             | <- blank ends
+---------------------------------------------------------------+
```

The "header row" lives at zero-indexed row 0 (which the user sees as
spreadsheet row 1) and the data table begins at column index 4 (column
E). Columns A–D on the data sheets are reserved for human-readable
labels and are ignored by the parser. The first three data columns
must include `Name`, `System Name`, and `System Number` (in any
order); remaining columns are tag columns.

Per-sheet config values (`Tag Provider`, `Site Name`, `UDT Type`,
`Folder`) live in **column C** — column B carries the human-readable
label like `Tag Provider:` and is ignored by the parser.

> **Indexing reminder for developers**: The reference Jython uses Apache
> POI which is 0-indexed. openpyxl (used by the Python port) is
> 1-indexed. POI `row=1, col=2` (zero-based) corresponds to openpyxl
> `row=2, column=3` (one-based) — both refer to spreadsheet cell **C2**
> (column C is the third column from A). This is the cell the Jython
> reads for the tag provider, site name, UDT type id, and folder name.

---

## Sheet 0 — Header sheet

Used only for the global provider and site name.

| Cell | Meaning           | Example          | Notes                       |
|------|-------------------|------------------|-----------------------------|
| B2   | Provider label    | `Tag Provider:`  | Optional, parser ignores it |
| C2   | Tag provider name | `Athens`         | **Read by the parser**      |
| B3   | Site label        | `Site Name:`     | Optional, parser ignores it |
| C3   | Site name         | `UFP_Athens`     | **Read by the parser**      |

All other cells on Sheet 0 are ignored. Sheet 0 is never treated as a
UDT data sheet, regardless of its name.

Both C2 and C3 are **required**. A blank value in either is a hard
error.

---

## Sheets 1..N — UDT data sheets

One sheet per UDT type being instantiated. Sheet names are not used by
the parser, so name them whatever is clear to the user
(`Tank Levels`, `Pumps`, etc.).

### Sheet header cells

| Cell | Meaning                | Example                    | Notes                |
|------|------------------------|----------------------------|----------------------|
| B2   | UDT type label         | `UDT Type:`                | Optional, ignored    |
| C2   | Full UDT type id       | `Tank/Tank Level Sensors`  | **Read by parser**   |
| B3   | Folder label           | `Folder:`                  | Optional, ignored    |
| C3   | Destination folder     | `LevelSensors`             | **Read by parser**   |

The UDT type id uses slashes to express nested type folders in
Ignition's `_types_` library. The destination folder is the leaf folder
under which instances on this sheet are placed.

Both C2 and C3 are **required**. Blank → hard error.

### Data table

The data table starts at zero-indexed row 0 (spreadsheet row 1) and
zero-indexed column 4 (spreadsheet column E).

**Required header columns** — these three must appear in the first
three positions, in **any order**:

* `Name`           — the UDT instance name
* `System Name`    — first path segment
* `System Number`  — second path segment

Production workbooks typically use the order `System Name`,
`System Number`, `Name`; the original Phase 3a spec said
`Name, System Name, System Number` but the Jython doesn't enforce
either order (it skips three positions and looks up by name), so the
parser accepts both.

**Optional tag columns** (any number, in any order, after the three
required ones): one column per atomic tag inside the UDT instance.

Column header termination: the parser reads columns from index 4
rightward and stops at the first blank header cell.

Row termination: data rows start at row 1 and continue until the
first row where the `Name` column is blank or empty.

### Dot notation = nested folders

A dot in a tag column header creates folders inside the UDT instance.

| Header           | Result                                             |
|------------------|----------------------------------------------------|
| `Raw Min`        | atomic tag `Raw Min` at the instance root          |
| `Status.Running` | folder `Status` containing atomic tag `Running`    |
| `Setpoints.High.HH` | folders `Setpoints/High` containing atomic tag `HH` |

Two headers that share a prefix (e.g. `Status.Running` and
`Status.Fault`) merge into a single `Status` folder containing both
tags.

### Empty cells are skipped

A blank/empty cell in a tag column means "do not emit this tag for
this row." The resulting instance config will not contain the
tag — the tag is *absent*, not present with an empty binding. This
matches the Jython behavior.

### Numeric cells

Numeric cell values that round-trip exactly as integers
(e.g. Excel stores `550` as `550.0`) are coerced to integer string form
in the OPC item path: the binding is `ns=1;s=[{plc}]550`, not
`ns=1;s=[{plc}]550.0`.

---

## Output path structure

For each data row, the UDT instance is configured at the Ignition path:

```
[<provider>]<site>/<System Name>/<System Number>/<folder>/<Name>
```

with `typeId = <Sheet B2 value>` and one atomic tag per non-empty tag
column. Every tag's `opcItemPath` is parameter-bound to
`ns=1;s=[{plc}]<cell value>`. The `{plc}` parameter is resolved at the
UDT type level — every type in the gateway library has a
`parameters.plc` default.

---

## Output JSON shape (the contract)

The downloaded file is a single nested folder tree, rooted at the site
name. This is exactly the shape Ignition Designer's Tag Browser
**Import** expects (and what `system.tag.exportTags(...)` produces).

```json
{
  "name": "UFP_Athens",
  "tagType": "Folder",
  "tags": [
    {
      "name": "A1",
      "tagType": "Folder",
      "tags": [
        {
          "name": "01",
          "tagType": "Folder",
          "tags": [
            {
              "name": "LevelSensors",
              "tagType": "Folder",
              "tags": [
                {
                  "name": "Tank 1",
                  "typeId": "Tank/Tank Level Sensors",
                  "tagType": "UdtInstance",
                  "tags": [
                    {
                      "name": "Raw Min",
                      "tagType": "AtomicTag",
                      "opcItemPath": {
                        "bindType": "parameter",
                        "binding": "ns=1;s=[{plc}]500"
                      }
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Notes:

* The `[<provider>]` prefix is **not** in the file. Designer asks
  which tag provider to import into at import time.
* Path segments derived from the workbook (`<sys_name>`, `<sys_num>`,
  the folder from cell C3) become nested `Folder` nodes.
* If the workbook's C3 folder cell contains slashes (`Edge/Pumps`),
  those split into nested folders.
* Every leaf tag carries `"tagType": "AtomicTag"` — required by the
  import dialog. Other fields (`dataType`, `valueSource`, `opcServer`,
  etc.) are inherited from the UDT type definition at resolve time.
* Folder dicts have `name`, `tagType: "Folder"`, and `tags`.
* UDT instances have `name`, `typeId`, `tagType: "UdtInstance"`,
  and `tags`.
* Empty cell values produce no tag dict at all.

---

## Validation

The builder collects warnings and errors as it parses.

### Errors (the request is rejected with HTTP 400)

* Workbook has fewer than 2 sheets.
* Sheet 0 C2 (provider) or C3 (site) is blank.
* A data sheet's C2 (UDT type) or C3 (folder) is blank.
* A data sheet is missing any of `Name`, `System Name`, `System Number`
  from its first three columns.

### Warnings (the request succeeds, but the report flags them)

* A data sheet has zero data rows. The Jython would silently iterate
  zero rows for such a sheet; we surface it as a warning so the
  engineer notices the sheet was effectively skipped.
* Duplicate `(System Name, System Number, Name)` tuples across the
  workbook.
* A data row has every tag cell blank (instance would have zero atomic
  tags — possibly intentional, possibly a mistake).
* A tag column header contains characters Ignition disallows inside a
  single tag segment (`. / \ [ ] " '` — note that `.` is allowed only
  as the folder separator, never inside a segment).
* A cell value contains whitespace or control characters that may be
  problematic in an OPC item path.

---

## Download format

The Tag Builder delivers a single `.json` file — a rooted folder tree
in Ignition's import/export format (see the next section for the full
shape). To use it:

1. Click **Download JSON** in the UI.
2. In Ignition Designer, open the Tag Browser, pick the tag provider
   you want to import into, right-click the destination folder, and
   choose **Import**.
3. Select the downloaded `.json` file. Designer merges the tree under
   the destination, creating intermediate folders as needed.

The validation report (warnings only — errors fail the request before
download) shows in the UI panel and is not duplicated in the file.

## Prerequisites for using the generated JSON

Before importing the generated JSON in Ignition, the gateway **must
already have the referenced UDT types loaded**. This tool generates
UDT *instances* only. UDT *type definitions* are imported separately
into Ignition Designer: Tag Browser → right-click `_types_` → Import.

If a `typeId` referenced by a generated instance does not exist on the
gateway, the import will fail with an "unknown type" error. There is no
way for ProcessArc to detect this ahead of time; the engineer is
responsible for keeping the gateway's type library in sync.
