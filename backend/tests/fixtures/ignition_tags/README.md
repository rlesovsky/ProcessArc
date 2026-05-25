# Ignition Tag Builder — Golden Fixture

This directory holds the contract test fixture for
`backend/features/ignition_tags`.

## Files

* `golden_input.xlsx` — A small but representative workbook covering:
  - The header sheet (provider + site).
  - A `Tank Level Sensors` data sheet with three rows (one fully
    populated, one fully populated, one with two blank tag cells to
    exercise the "empty cell → skip tag" rule).
  - A `Pumps` data sheet with dot-notation tag columns to exercise
    nested folders (`Status.Running`, `Status.Fault`,
    `Setpoints.High.HH`).
* `golden_expected_bundle.json` — The deterministic, sorted bundle the
  builder must produce for `golden_input.xlsx`. Sorted by
  `(base_path, instance.name)`; tag lists within each instance and
  folder are sorted by `name` (the `bundle_for_comparison` helper in
  the test applies the same sort to the actual output before
  comparing).

## Owner

These fixtures are synthetic and generated to match the contract in
[docs/ignition_tag_template_spec.md](../../../../docs/ignition_tag_template_spec.md).

If the user supplies a real production fixture pair
(`golden_input.xlsx` + `golden_expected_bundle.json`) later, replace
both files here. The test in `backend/tests/test_ignition_tags.py`
reads them by name; no other code changes are needed.

## Regenerating

The synthetic fixture was produced by a one-off generator script
captured in the git history (see the commit that introduced this
directory). If you need to regenerate, change the inputs in that
script and re-run it. Do not edit the xlsx by hand — keep the
generator as the single source of truth.
