# Commissioning Workbook Builder

Takes a customer "write-up" workbook (Graphics-and-Tables style) and
populates the canonical Commissioning Workbook template with the
mappings we can reliably derive.

## Public API

```python
from backend.features.commissioning_workbook import (
    parse_source, build_workbook,
)

parsed = parse_source(source_xlsx_bytes)
new_bytes, report = build_workbook(parsed, template_bytes)
```

`report` is a `BuildReport` — see `schema.py`. It exposes
`to_text_log()` which is what the frontend downloads as a sibling
`.txt` file.

## What gets mapped

| Source sheet | Template destination | Behavior |
|---|---|---|
| Chemical | Tank And Chem Number cols M / N | Adds Source K-Factor / Source Meter columns. Existing K Factor (col J) is never overwritten. |
| Cylinder 1 Sequencing | Treat Sequence Sign Off COMMENTS (col E) | Free-text narrative dropped into the matching `STEP n - <name>` header row. |
| Cylinder 2 Sequencing | Treat Sequence Sign Off COMMENTS | Same step-name match (template has one treat section). |
| Mix Sequencing | Mix Sequence Sign Off COMMENTS | Same pattern. |
| Cylinder 1/2 Treat Graphic | Treat Sequence Sign Off (STEP 1 row) COMMENTS | Graphic-level notes; short summary. |
| Mix Graphic | Mix Sequence Sign Off (MIX 1 SEQUENCE row) COMMENTS | Same as above. |
| Plant Info / Operators / Tank Info | Network Schema (new rows) | Each fact gets its own row at the bottom with col A="Plant fact". |

Anything we don't recognize lands in `BuildReport.warnings`.

## Non-destructive contract

The builder never overwrites a populated template cell. When it tries
to write into a non-empty cell, the attempt is recorded as a
`ChangeLogEntry` with `conflict=True` and the new value is *not*
written. Reviewers can resolve the conflict by hand in the populated
workbook (compare cols J and M for K-Factors, for example).

## Bundled template

The default template ships at:
```
backend/features/commissioning_workbook/templates/default_commissioning_workbook.xlsx
```

It's bundled into the Windows .exe via the `datas` entry in
`processarc.spec` and served by `GET
/api/commissioning-workbook/default-template`. Swap that file out and
re-tag a release to ship a new canonical template.
