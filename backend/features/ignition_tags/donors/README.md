# Donor library — Plant Bundle Builder

Committed JSON fragments that the `POST /api/ignition-tags/build-plant`
endpoint composes into a full Ignition tag bundle for a new UFP plant.

See the Plant Bundle Builder feature design for the full picture
(committed donor extraction, the substitution rules, why these files
exist rather than per-plant golden exports, etc.).

## Files

| File                 | Branch       | Source plant       | Notes                              |
|----------------------|--------------|--------------------|------------------------------------|
| `cylinders_1.json`   | cylinders=1  | Derived from `cylinders_2.json` | single numbered child folder: `1` (see "Single-system donors" below) |
| `cylinders_2.json`   | cylinders=2  | Bartow FL 523      | numbered child folders: `1`, `2`   |
| `cylinders_3.json`   | cylinders=3  | Athens AL 527      | numbered child folders: `1`, `2`, `3` |
| `mixing_1.json`      | mixing=1     | Derived from `mixing_2.json`    | single numbered child folder: `1` (see "Single-system donors" below) |
| `mixing_2.json`      | mixing=2     | Athens AL 527      | numbered child folders: `1`, `2`   |
| `mixing_3.json`      | mixing=3     | Bartow FL 523      | numbered child folders: `1`, `2`, `3` |
| `plant_level.json`   | plant_level  | Bartow FL 523      | four top-level folders: `Plant Info`, `Treating Data`, `Offline SQL`, `Production` |
| `*.json.log`         | —            | —                  | extraction-time audit log (see below) |

## Placeholder tokens

Every plant-specific string is replaced with one of six tokens at
extraction time. The substitution engine resolves them at build time
from the request body's plant identity. The recognized set is enforced
by [`donor.py`](../donor.py):

| Token                    | Resolves to                              | Example         |
|--------------------------|------------------------------------------|-----------------|
| `__SITE_LONG__`          | full plant name                          | `Fairless Hills PA 532` |
| `__SITE_SHORT__`         | plant short name                         | `Fairless Hills`        |
| `__PLANT_NUM__`          | 3-digit plant number                     | `532`                   |
| `__REGION_CODE__`        | two-letter state code                    | `PA`                    |
| `__MQTT_TOPIC__`         | full MQTT topic (UFP convention)         | `UFP Industries/532-Fairless Hills/PTS` |
| `__MAIN_PROJECT_NAME__`  | named-query main project name            | `_532_Fairless Hills`   |

Adding a token requires:
1. Adding it to `RECOGNIZED_PLACEHOLDERS` in `donor.py`
2. Returning the resolved value from `PlantIdentity.as_replacements()` in `substitutor.py`
3. Re-running extraction so existing donors pick up the new token

## Extraction procedure

Donors are produced one-time by the extraction script:

```sh
python -m backend.features.ignition_tags.scripts.extract_donor \
    --source path/to/<plant-name>.json \
    --branch cylinders \
    --site-short Athens \
    --site-long "Athens AL 527" \
    --plant-num 527 \
    --region-code AL \
    --out backend/features/ignition_tags/donors/cylinders_3.json
```

The script performs three defensive passes (each logged in the sibling
`.log` file):

1. **Bracket cleanup** on every `opcItemPath` (both the string and
   dict-form). Anything other than `{plc}`/`{PLC}`/`m{plc}` is treated
   as either the canonical source plant or a leak from a prior
   copy-and-replace cycle, and rewritten to `__SITE_SHORT__`.
2. **Datasource and historyProvider cleanup**, same defensive rule.
   Constants `'lansing'` and `''` pass through; everything else
   becomes `__SITE_SHORT__`.
3. **`[SCADA]<plant-long-name>/...` cleanup** on every string field.
   Catches cross-plant `sourceTagPath` and `expression` references that
   reference another plant's SCADA tree.

Plant-specific compound strings (`Athens AL 527`, `UFP Industries/527-Athens/PTS`,
`_527_Athens`, the bare `Athens` short name) are replaced with their
matching placeholder tokens in that order — longest first to avoid
double-substitution.

`Plant Info` per-tag overrides write the placeholder into specific
fields (`value` on `Plant Number`, `datasource` on `RegionNumber` /
`CustomerNumber`) even when the generic rules would have missed them.

For Bartow specifically, the top-level `Tram` folder is dropped — it
is a Bartow-only subsystem (its own PLC) and does not belong in any
reusable donor.

## What the `.log` file captures

Each donor commits with a sibling `.log` file that records:

- Source plant (name + path of the export the donor came from)
- Tag counts by `tagType` in the extracted fragment
- All in-string substitutions (which compound patterns matched, how many times)
- All bracket rewrites (raw bracket name → `__SITE_SHORT__`), marked canonical or LEAK
- All datasource and historyProvider rewrites (same marking)
- All `[SCADA]<long-name>/` rewrites (same marking)
- Any Plant Info per-path overrides applied
- Any subtrees dropped (e.g. Bartow's `Tram`)
- Anomalies — leftover literals of the source plant after substitution

The log is purely documentation. The runtime loader (`donor.py`)
ignores it. Its purpose is to give the next maintainer enough context
to redo the extraction, audit a suspicious result, or understand why a
particular rewrite happened.

## Single-system donors

`cylinders_1.json` and `mixing_1.json` are derived files, not directly
extracted from a source plant. They were created for the Union City
build — the first single-system plant project — by trimming the
count=2 donors:

- `mixing_1.json` is `mixing_2.json` filtered to just the folder named
  `"1"` (37 children, from Athens AL 527's system 1).
- `cylinders_1.json` is `cylinders_2.json` filtered to just the folder
  named `"1"` (5 children, from Bartow FL 523's system 1).

Both files carry `_derived_from` / `_derived_note` keys recording
their provenance so a future re-extraction (when a clean canonical
single-system plant becomes available) can replace them. They pass
the same placeholder validation as the directly-extracted donors.

## Re-extracting a donor

Re-run the extraction when:

- A bug is found in the donor (a missing tag, a wrong-typed value)
- A UFP-wide standard changes (a new alarm becomes part of every plant)
- A cleaner source plant becomes available than the one originally used

Day-to-day plant builds do not require donor changes. The donors are
stable inputs.
