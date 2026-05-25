# `backend/features/ignition_tags` — Ignition Tag Builder

Deterministic Excel → Ignition UDT-instance JSON transformer. This is
a Python port of a production Jython script that runs inside Ignition
Perspective (see "Reference implementation" below).

For the template contract see
[docs/ignition_tag_template_spec.md](../../../docs/ignition_tag_template_spec.md).
For architecture/scope see
[docs/ignition_tag_builder_architecture.md](../../../docs/ignition_tag_builder_architecture.md).

## Module layout

| File          | Role                                                                   |
|---------------|------------------------------------------------------------------------|
| `schema.py`   | Pydantic models for the output contract (`extra='forbid'` on instances)|
| `parser.py`   | openpyxl-based workbook reader; emits `ParsedWorkbook`                 |
| `builder.py`  | `build_nested_structure` port + per-row instance assembly              |
| `packager.py` | `build_ignition_tree(instances)` → rooted folder tree in Ignition's import format |
| `router.py`   | `POST /api/ignition-tags/build` — wired in `backend/api/main.py`       |

## Running the tests

```sh
# From the ProcessArc/ project root
source backend/.venv/bin/activate
pytest backend/tests/test_ignition_tags.py -v
```

The golden contract test reads
`backend/tests/fixtures/ignition_tags/golden_input.xlsx` and compares
the builder's output against `golden_expected_bundle.json`. If you
replace the synthetic fixture with a real production
`(input.xlsx, expected_bundle.json)` pair from the user, the test
picks it up automatically — no code change required.

## POI ↔ openpyxl indexing

The reference Jython uses Apache POI, which is 0-indexed for both
rows and columns. openpyxl is 1-indexed. There is exactly one
overlap: the user-visible spreadsheet row/column number, which is what
we use in error messages.

| Cell | POI (Jython)       | openpyxl (Python)  |
|------|--------------------|--------------------|
| B2   | row=1, col=1       | row=2, column=2    |
| C2   | row=1, col=2       | row=2, column=3    |
| C3   | row=2, col=2       | row=3, column=3    |
| E1   | row=0, col=4       | row=1, column=5    |

The Jython reads `get_cell_value(file, row=1, col=2)` to fetch the
provider name, site name, UDT type id, and folder. Because POI col=2
is the third column (zero-indexed), this is **cell C2** — *not* B2.
Column B carries human-readable labels like `Tag Provider:` and is
ignored by the parser. See `parser.CONFIG_VALUE_COLUMN`.

The data table on a data sheet starts at POI `row=0, col=4`, which is
openpyxl `row=1, column=5` — cell E1. See `parser.DATA_HEADER_ROW` and
`parser.DATA_FIRST_COLUMN`.

## Required-column order

The first three columns of a data sheet must include `Name`,
`System Name`, and `System Number`, in **any order**. The Jython does
positional `[3:]` to slice off the first three columns as tag columns,
then accesses the three special columns by name via
`ds.getValueAt(row, "Name")`. The Python port matches that: it
verifies the three are present in any of the first three slots, then
looks them up by name from the parsed row dict.

## Validation rules

Errors (fail the request with HTTP 400, `validation_report` in the
JSON body):

* `workbook.too_few_sheets`
* `header.missing_provider`
* `header.missing_site`
* `sheet.missing_udt_type`
* `sheet.missing_folder`
* `sheet.missing_required_column`
* `sheet.no_data_rows`

Warnings (request succeeds, surfaced in `validation_report.json`):

* `duplicate_instance` — same `(System Name, System Number, Name)` on
  two rows.
* `row.no_tags` — all tag cells blank.
* `header.disallowed_tag_chars` — tag column header segment contains
  characters Ignition disallows inside a single segment.
* `value.suspicious_chars` — a tag cell value contains whitespace or
  control characters.

## Reference implementation

This Python port is structurally faithful to the production Jython
script below. If the port and this script disagree on behavior, the
Jython wins — fix the port, not this snippet.

```python
import org.apache.poi.ss.usermodel.WorkbookFactory as WorkbookFactory
import org.apache.poi.ss.usermodel.DateUtil as DateUtil
from java.io import ByteArrayInputStream

def get_sheet_count(fileBytes):
    fileStream = ByteArrayInputStream(fileBytes)
    wb = WorkbookFactory.create(fileStream)
    value = wb.getNumberOfSheets()
    fileStream.close()
    return value

def get_cell_value(fileBytes, row, col, sheetNum=0):
    # Returns typed value: date | int | float | str | bool | None
    ...

def table_to_dataset(fileBytes, hasHeaders=False, sheetNum=0, firstRow=None,
                     lastRow=None, firstCol=None, lastCol=None):
    # Auto-detects lastRow by first blank in column `firstCol`.
    # Auto-detects lastCol by first blank in row `firstRow`.
    # Returns Ignition Dataset with headers from row `firstRow`.
    ...

def build_nested_structure(folder_dict, path_list, tag_name, value):
    if not path_list:
        if not value:
            return
        folder_dict.append({
            "name": tag_name,
            "opcItemPath": {
                "bindType": "parameter",
                "binding": "ns=1;s=[{plc}]" + str(value),
            }
        })
        return
    folder_name = path_list[0]
    folder = next(
        (f for f in folder_dict
         if f["name"] == folder_name and f["tagType"] == "Folder"),
        None,
    )
    if folder is None:
        folder = {"name": folder_name, "tagType": "Folder", "tags": []}
        folder_dict.append(folder)
    build_nested_structure(folder["tags"], path_list[1:], tag_name, value)

excel_upload   = event.file.getBytes()
sheet_count    = get_sheet_count(excel_upload)
tag_provider   = get_cell_value(excel_upload, row=1, col=2)   # Sheet 0, B2
site_name      = get_cell_value(excel_upload, row=2, col=2)   # Sheet 0, B3

for sheet in range(sheet_count):
    if sheet == 0:
        continue
    ds = table_to_dataset(
        excel_upload, hasHeaders=True, sheetNum=sheet, firstRow=0, firstCol=4,
    )
    udt_type = get_cell_value(excel_upload, row=1, col=2, sheetNum=sheet)
    folder   = get_cell_value(excel_upload, row=2, col=2, sheetNum=sheet)

    for row in range(ds.getRowCount()):
        udt_instance_name = ds.getValueAt(row, "Name")
        udt_tags          = []
        sys_name          = str(ds.getValueAt(row, "System Name"))
        sys_num           = str(ds.getValueAt(row, "System Number"))
        base_path = "[{}]{}/{}/{}/{}".format(
            tag_provider, site_name, sys_name, sys_num, folder,
        )
        tag_cols = ds.getColumnNames().toArray()[3:]

        for col in tag_cols:
            path_parts     = col.split(".")
            tag_name       = path_parts[-1]
            parent_folders = path_parts[:-1]
            tag_value      = ds.getValueAt(row, col)
            build_nested_structure(udt_tags, parent_folders, tag_name, tag_value)

        tag_config = {
            "name":    udt_instance_name,
            "typeId":  udt_type,
            "tagType": "UdtInstance",
            "tags":    udt_tags,
        }
        system.tag.configure(base_path, tag_config, "o")
```
