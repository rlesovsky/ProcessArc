"""Commissioning Workbook Builder feature.

Companion to the Ignition Tag Builder: takes a plant-specific "write-up"
workbook (typically the Graphics-and-Tables style xlsx) and populates a
canonical Commissioning Workbook template (the multi-sheet sign-off
document) with the mappings we can reliably derive from the source.

The builder is intentionally non-destructive — it never overwrites a
cell that already has a value. Conflicts are surfaced as change-log
entries so a commissioning engineer can review and resolve them.

Public surface:
    parse_source(bytes) -> ParsedSource
    build_workbook(parsed, template_bytes) -> (xlsx bytes, change_log)
"""

from .builder import build_workbook
from .parser import parse_source
from .schema import ChangeLogEntry, ParsedSource, BuildReport

__all__ = [
    "build_workbook",
    "parse_source",
    "ChangeLogEntry",
    "ParsedSource",
    "BuildReport",
]
