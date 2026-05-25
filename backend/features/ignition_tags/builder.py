"""UDT instance assembly for the Ignition Tag Builder.

Port of the build_nested_structure / per-row loop from the reference
Jython script. The output of `build_all` is structurally identical to
what `system.tag.configure(base_path, tag_config, "o")` would have
written for the same workbook.
"""

from __future__ import annotations

import re
from typing import Any

from .parser import REQUIRED_COLUMNS, ParsedWorkbook, SheetData
from .schema import (
	AtomicTag,
	FolderTag,
	InstanceConfig,
	InstanceWithPath,
	OpcItemPath,
	ValidationIssue,
	ValidationReport,
)

# Characters that Ignition disallows inside a single tag segment. The
# dot is allowed in a column header as the folder separator but never
# inside an individual segment after splitting.
DISALLOWED_TAG_SEGMENT_CHARS = re.compile(r"""[./\\\[\]"']""")
SUSPICIOUS_OPC_VALUE_CHARS = re.compile(r"[\s\x00-\x1f]")


def _stringify_cell_value(value: Any) -> str:
	"""Convert a cell value to the string the OPC binding embeds.

	Numeric values that round-trip exactly as int become integer
	strings — matches the Jython `if value == int(value): value = int(value)`
	guard, so an Excel-typed `550.0` becomes `"550"`, not `"550.0"`.
	"""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, float) and value == int(value):
		return str(int(value))
	return str(value)


def build_nested_structure(
	folder_list: list[dict],
	path_parts: list[str],
	tag_name: str,
	value: Any,
) -> None:
	"""Direct port of the reference Jython `build_nested_structure`.

	Mutates `folder_list` in place. Skips entirely on empty `value`
	(blank cell) — matches `if not value: return` in the Jython.

	The function deliberately returns dicts (not pydantic models)
	because the recursive in-place mutation is much simpler with plain
	dicts. The final instance dict is validated against
	`InstanceConfig` by `build_instance`.
	"""
	# Skip on falsy values — matches the Jython `if not value: return`
	# exactly. This includes 0, 0.0, "" and False as well as None;
	# users who want a literal "0" in the binding cannot get it via this
	# tool (same as the production Jython).
	if not value:
		return

	if not path_parts:
		folder_list.append(
			{
				"name": tag_name,
				"tagType": "AtomicTag",
				"opcItemPath": {
					"bindType": "parameter",
					"binding": "ns=1;s=[{plc}]" + _stringify_cell_value(value),
				},
			}
		)
		return

	folder_name = path_parts[0]
	folder = next(
		(
			f
			for f in folder_list
			if f.get("name") == folder_name and f.get("tagType") == "Folder"
		),
		None,
	)
	if folder is None:
		folder = {"name": folder_name, "tagType": "Folder", "tags": []}
		folder_list.append(folder)
	build_nested_structure(folder["tags"], path_parts[1:], tag_name, value)


def _build_instance_dict(
	row: dict[str, Any],
	udt_type: str,
	headers: list[str],
) -> dict[str, Any]:
	"""Assemble one raw instance dict from a parsed row.

	`headers` is the full header list; the first three are always
	some permutation of `Name`, `System Name`, `System Number` (checked
	in the parser). The values are looked up by name from `row`, so the
	column order doesn't matter — matches the Jython, which does the
	same name-based lookup via `ds.getValueAt(row, "Name")`.
	"""
	instance_name = str(row[REQUIRED_COLUMNS[0]])

	tag_columns = headers[len(REQUIRED_COLUMNS):]
	tags: list[dict] = []
	for col in tag_columns:
		path_parts = col.split(".")
		tag_name = path_parts[-1]
		parent_folders = path_parts[:-1]
		build_nested_structure(tags, parent_folders, tag_name, row.get(col))

	return {
		"name": instance_name,
		"typeId": udt_type,
		"tagType": "UdtInstance",
		"tags": tags,
	}


def _validate_tag_segments(headers: list[str], sheet_name: str) -> list[ValidationIssue]:
	"""Warn on tag headers whose individual segments contain disallowed chars."""
	issues: list[ValidationIssue] = []
	for col in headers[len(REQUIRED_COLUMNS):]:
		for segment in col.split("."):
			if DISALLOWED_TAG_SEGMENT_CHARS.search(segment):
				issues.append(
					ValidationIssue(
						severity="warning",
						code="header.disallowed_tag_chars",
						message=(
							f"Tag column header {col!r} contains a segment "
							f"{segment!r} with characters Ignition disallows."
						),
						sheet=sheet_name,
						column=col,
					)
				)
				break
	return issues


def _scan_row_for_warnings(
	row: dict[str, Any], headers: list[str], sheet_name: str
) -> list[ValidationIssue]:
	"""Per-row warnings (no atomic tags, suspicious OPC characters)."""
	issues: list[ValidationIssue] = []
	tag_columns = headers[len(REQUIRED_COLUMNS):]

	# All tag columns blank — instance has zero atomic tags.
	if tag_columns and all(
		row.get(c) in (None, "") for c in tag_columns
	):
		issues.append(
			ValidationIssue(
				severity="warning",
				code="row.no_tags",
				message=(
					f"Row for instance {row[REQUIRED_COLUMNS[0]]!r} on sheet "
					f"{sheet_name!r} has every tag column blank — the "
					"resulting instance will have zero atomic tags."
				),
				sheet=sheet_name,
				row=row.get("__row__"),
			)
		)

	# Suspicious characters in any tag cell.
	for col in tag_columns:
		value = row.get(col)
		if isinstance(value, str) and SUSPICIOUS_OPC_VALUE_CHARS.search(value):
			issues.append(
				ValidationIssue(
					severity="warning",
					code="value.suspicious_chars",
					message=(
						f"Cell value {value!r} in column {col!r} contains "
						"whitespace or control characters; the resulting OPC "
						"item path may be invalid."
					),
					sheet=sheet_name,
					row=row.get("__row__"),
					column=col,
				)
			)

	return issues


def _sheet_to_instances(
	sheet: SheetData, provider: str, site: str
) -> tuple[list[InstanceWithPath], list[ValidationIssue]]:
	issues: list[ValidationIssue] = []
	issues.extend(_validate_tag_segments(sheet.headers, sheet.sheet_name))
	out: list[InstanceWithPath] = []
	for row in sheet.rows:
		issues.extend(_scan_row_for_warnings(row, sheet.headers, sheet.sheet_name))
		sys_name = str(row[REQUIRED_COLUMNS[1]])
		sys_num = str(row[REQUIRED_COLUMNS[2]])
		base_path = f"[{provider}]{site}/{sys_name}/{sys_num}/{sheet.folder}"
		raw = _build_instance_dict(row, sheet.udt_type, sheet.headers)
		instance = InstanceConfig.model_validate(raw)
		out.append(
			InstanceWithPath(
				base_path=base_path,
				source_sheet=sheet.sheet_name,
				source_row=int(row["__row__"]),
				instance=instance,
			)
		)
	return out, issues


def _duplicate_warnings(instances: list[InstanceWithPath]) -> list[ValidationIssue]:
	"""Warn on duplicate (System Name, System Number, Name) tuples.

	The system-name + system-number live inside the base path already,
	so duplicates show up as identical `base_path + instance.name`
	pairs — same target Ignition path.
	"""
	seen: dict[tuple[str, str], list[InstanceWithPath]] = {}
	for inst in instances:
		key = (inst.base_path, inst.instance.name)
		seen.setdefault(key, []).append(inst)
	issues: list[ValidationIssue] = []
	for key, group in seen.items():
		if len(group) > 1:
			base_path, name = key
			rows = ", ".join(f"{g.source_sheet}:row {g.source_row}" for g in group)
			issues.append(
				ValidationIssue(
					severity="warning",
					code="duplicate_instance",
					message=(
						f"Duplicate UDT instance path {base_path}/{name} "
						f"defined in: {rows}."
					),
				)
			)
	return issues


def build_all(parsed: ParsedWorkbook) -> tuple[list[InstanceWithPath], ValidationReport]:
	"""Assemble every UDT instance config defined in the workbook.

	Returns the list of `(base_path, instance)` plus a full validation
	report (errors carried over from parsing, warnings from this stage).
	"""
	errors = [i for i in parsed.issues if i.severity == "error"]
	warnings = [i for i in parsed.issues if i.severity == "warning"]

	if errors or parsed.provider is None or parsed.site is None:
		# Don't try to build anything if the structural prerequisites
		# failed; the router will surface `errors` as a 400.
		return [], ValidationReport(errors=errors, warnings=warnings)

	instances: list[InstanceWithPath] = []
	for sheet in parsed.sheets:
		sheet_instances, sheet_issues = _sheet_to_instances(
			sheet, parsed.provider, parsed.site
		)
		instances.extend(sheet_instances)
		for issue in sheet_issues:
			if issue.severity == "error":
				errors.append(issue)
			else:
				warnings.append(issue)

	warnings.extend(_duplicate_warnings(instances))

	return instances, ValidationReport(errors=errors, warnings=warnings)


