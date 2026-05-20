"""Smoke test against the real Fairless Hills workbook.

Run from the ProcessArc/ project root:
    source backend/.venv/bin/activate && python -m backend.tests.smoke_fairless [--workbook PATH]

This is not a pytest test (yet); it's a script that prints what we discovered
and asserts the headline facts from the Fairless Hills read file.

Workbook path resolution, in order of precedence:
  1. --workbook CLI arg
  2. SMOKE_WORKBOOK environment variable
  3. ../Fairless Hills Graphics and Sequence.xlsx (one level up from ProcessArc/)
  4. ./Fairless Hills Graphics and Sequence.xlsx (alongside ProcessArc/)

If none of those exist, the script exits with a clear error.
"""

import argparse
import os
import sys
from pathlib import Path

from backend.config import discover_plant_configuration
from backend.ingest import ingest_workbook


DEFAULT_NAME = "Fairless Hills Graphics and Sequence.xlsx"

# Candidate locations the test will try in order. The two relative paths cover
# the engineer running from ProcessArc/ when the workbook is either alongside
# the repo (typical local layout) or in the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CANDIDATES = [
    _REPO_ROOT.parent / DEFAULT_NAME,  # ../Fairless Hills...xlsx
    _REPO_ROOT / DEFAULT_NAME,         # ./Fairless Hills...xlsx
]


def _resolve_workbook(arg_path: str | None) -> Path:
    if arg_path:
        return Path(arg_path).expanduser()
    env_path = os.environ.get("SMOKE_WORKBOOK")
    if env_path:
        return Path(env_path).expanduser()
    for cand in _DEFAULT_CANDIDATES:
        if cand.exists():
            return cand
    # Fall back to the first candidate so the error message is concrete.
    return _DEFAULT_CANDIDATES[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        help="Path to the Fairless Hills sequence workbook (.xlsx).",
    )
    args = parser.parse_args()

    FH = _resolve_workbook(args.workbook)
    if not FH.exists():
        print(
            f"Workbook not found: {FH}\n"
            f"  Pass --workbook PATH, set SMOKE_WORKBOOK=PATH, or place the file at one of:\n"
            + "\n".join(f"    {c}" for c in _DEFAULT_CANDIDATES),
            file=sys.stderr,
        )
        return 2

    wb = ingest_workbook(FH)
    pc = discover_plant_configuration(wb)

    print(f"\nSite:     {pc.site_name}")
    print(f"Workbook: {pc.workbook_filename}")
    print(f"Sheets:   {len(pc.all_sheets)} total, {len(pc.sequence_sheets)} sequencing")

    print("\nCylinders:")
    for c in pc.cylinders:
        flag = " [IDLE]" if c.is_idle else ""
        print(f"  #{c.number}  '{c.name}'  sheet={c.sequence_sheet!r}{flag}")

    print("\nMix systems:")
    for m in pc.mix_systems:
        print(f"  #{m.number}  '{m.name}'  chemistry={m.chemistry!r}  sheet={m.sequence_sheet!r}")

    print(f"\nTanks: {len(pc.tanks)}")
    for t in pc.tanks:
        idle = " [IDLE]" if t.is_idle else ""
        print(
            f"  tank_id={t.tank_id!r:14}  chem={t.chemical!r:14}  cyl={t.cylinder_used}  "
            f"min={t.min_volume}  max={t.max_volume}  target={t.target_volume}{idle}"
        )

    print(f"\nWarnings ({len(pc.warnings)}):")
    for w in pc.warnings:
        print(f"  - {w}")

    # ----- assertions from the Fairless Hills read file --------------------
    failures: list[str] = []

    cyl_numbers = sorted(c.number for c in pc.cylinders)
    if cyl_numbers != [1, 2]:
        failures.append(f"expected cylinders [1, 2], got {cyl_numbers}")

    active = sorted(c.number for c in pc.active_cylinders)
    if active != [1, 2]:
        failures.append(f"expected active cylinders [1, 2], got {active}")

    mix_names = [m.name for m in pc.mix_systems]
    if "ECO Mix" not in mix_names or "MCA Mix" not in mix_names:
        failures.append(f"expected ECO Mix + MCA Mix, got {mix_names}")

    if len(pc.tanks) != 11:
        failures.append(f"expected 11 tanks, got {len(pc.tanks)}")

    # Tank 1 = MCA, cylinder 1
    t1 = next((t for t in pc.tanks if t.raw.get("number") == 1), None)
    if t1 is None:
        failures.append("Tank 1 not found")
    else:
        if t1.chemical != "MCA":
            failures.append(f"Tank 1 expected chemical 'MCA', got {t1.chemical!r}")
        if t1.cylinder_used != 1:
            failures.append(f"Tank 1 expected cylinder 1, got {t1.cylinder_used}")

    # Tank 4 = idle
    t4 = next((t for t in pc.tanks if t.raw.get("number") == 4), None)
    if t4 is None or not t4.is_idle:
        failures.append(f"Tank 4 expected idle, got {t4}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nOK  — all Fairless Hills assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
