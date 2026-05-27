"""Orchestrator for the Plant Bundle Builder.

Pulls the right donors per the plant config, applies the substitution
rules, builds the wrapping site root folder, and (optionally) grafts in
the Pumps/Valves/Tanks UdtInstances that the existing xlsx builder
produces.

The xlsx integration calls into `build_all()` from the existing
`builder.py` module — that code stays untouched and remains the source
of truth for xlsx → UdtInstance conversion.
"""

from __future__ import annotations

from typing import Any

from .builder import build_all
from .donor import load_donor
from .packager import build_ignition_tree
from .parser import parse_workbook
from .schema import (
	InstanceConfig,
	InstanceWithPath,
	ValidationIssue,
	ValidationReport,
)
from .substitutor import (
	PlantIdentity,
	build_identity_from_request,
	build_renumber_map,
	substitute,
)


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


REQUIRED_PLANT_CONFIG_KEYS = ("site_long", "site_short", "plant_number", "region_code")


def _validate_plant_config(plant_config: dict[str, Any]) -> list[ValidationIssue]:
	"""Surface every required-field / shape problem in a single list.

	Errors here cause a 400 — the request never reaches the donor load.
	"""
	issues: list[ValidationIssue] = []

	for key in REQUIRED_PLANT_CONFIG_KEYS:
		val = plant_config.get(key)
		if val is None or (isinstance(val, str) and not val.strip()):
			issues.append(
				ValidationIssue(
					severity="error",
					code="plant_config.missing_required",
					message=f"Required field {key!r} is missing or empty.",
				)
			)

	for branch in ("cylinders", "mixing"):
		branch_cfg = plant_config.get(branch) or {}
		count = branch_cfg.get("count")
		if not isinstance(count, int) or not (1 <= count <= 3):
			issues.append(
				ValidationIssue(
					severity="error",
					code="plant_config.invalid_count",
					message=(
						f"{branch}.count must be an integer 1..3; got {count!r}."
					),
				)
			)
			continue
		numbering = branch_cfg.get("numbering")
		if numbering is not None:
			if not isinstance(numbering, list) or len(numbering) != count:
				issues.append(
					ValidationIssue(
						severity="error",
						code="plant_config.numbering_mismatch",
						message=(
							f"{branch}.numbering must be a list of length "
							f"{count} (matching {branch}.count). "
							f"Got {numbering!r}."
						),
					)
				)
				continue
			if not all(isinstance(n, int) and n > 0 for n in numbering):
				issues.append(
					ValidationIssue(
						severity="error",
						code="plant_config.numbering_mismatch",
						message=(
							f"{branch}.numbering must contain positive integers; "
							f"got {numbering!r}."
						),
					)
				)

	return issues


# ---------------------------------------------------------------------------
# Donor → substituted-fragment loading
# ---------------------------------------------------------------------------


def _load_and_substitute(
	branch: str,
	count: int | None,
	identity: PlantIdentity,
	cylinder_map: dict[int, int],
	mix_map: dict[int, int],
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
	"""Load one donor and apply substitutions. Surfaces a structured error
	if the donor file isn't on disk yet.
	"""
	try:
		donor_tags, donor_issues = load_donor(branch, count)
	except FileNotFoundError as exc:
		return [], [
			ValidationIssue(
				severity="error",
				code="donor.not_available",
				message=(
					f"No donor available for branch={branch!r}"
					+ (f", count={count}" if count is not None else "")
					+ f". {exc}"
				),
			)
		]

	if any(i.severity == "error" for i in donor_issues):
		return [], donor_issues

	substituted, sub_issues = substitute(
		donor_tags,
		identity=identity,
		branch=branch,
		cylinder_mapping=cylinder_map,
		mix_mapping=mix_map,
	)
	return substituted, donor_issues + sub_issues


# ---------------------------------------------------------------------------
# Tree assembly
# ---------------------------------------------------------------------------


def _assemble_site_root(
	site_long: str,
	cylinders_children: list[dict[str, Any]],
	mixing_children: list[dict[str, Any]],
	plant_level_children: list[dict[str, Any]],
) -> dict[str, Any]:
	"""Wrap the three substituted fragments under a single site root.

	The cylinders/mixing donors emit the numbered subfolders directly;
	this function rebuilds the wrapping `Cylinders` and `Mixing` parent
	folders. The plant-level donor's children are spliced in alongside
	those two.
	"""
	site_root: dict[str, Any] = {
		"name": site_long,
		"tagType": "Folder",
		"tags": [],
	}
	if cylinders_children:
		site_root["tags"].append(
			{
				"name": "Cylinders",
				"tagType": "Folder",
				"tags": cylinders_children,
			}
		)
	if mixing_children:
		site_root["tags"].append(
			{
				"name": "Mixing",
				"tagType": "Folder",
				"tags": mixing_children,
			}
		)
	site_root["tags"].extend(plant_level_children)
	return site_root


# ---------------------------------------------------------------------------
# Xlsx grafting
# ---------------------------------------------------------------------------


def _find_or_create_folder(parent: dict[str, Any], name: str) -> dict[str, Any]:
	for child in parent.get("tags", []):
		if child.get("name") == name and child.get("tagType") == "Folder":
			return child
	new_folder: dict[str, Any] = {"name": name, "tagType": "Folder", "tags": []}
	parent.setdefault("tags", []).append(new_folder)
	return new_folder


def _navigate(parent: dict[str, Any], segments: list[str]) -> dict[str, Any]:
	"""Walk `segments` from `parent`, creating any missing Folder along
	the way. Returns the leaf folder."""
	cursor = parent
	for seg in segments:
		cursor = _find_or_create_folder(cursor, seg)
	return cursor


def _strip_provider(base_path: str) -> str:
	"""`[SCADA]Bartow FL 523/Cylinders/1/Edge/Pumps` → `Bartow FL 523/Cylinders/1/Edge/Pumps`."""
	if base_path.startswith("["):
		end = base_path.find("]")
		if end != -1:
			return base_path[end + 1 :]
	return base_path


def _graft_xlsx_instances(
	site_root: dict[str, Any], instances: list[InstanceWithPath]
) -> list[ValidationIssue]:
	"""Replace the contents of the donor's Pumps/Valves/Tanks (or any
	other xlsx-defined sys_name/sys_num/folder triple) with the xlsx-
	built instances.

	Grouping is by (sys_name, sys_num, folder) — every xlsx row sharing
	that triple lives in the same leaf folder, so we wipe and refill the
	target folder once per group.

	If the xlsx points at a (sys_name, sys_num, folder) that doesn't
	exist in the donor tree, the folder structure is created on demand
	and a warning is surfaced. (An out-of-band sys_num like Cylinders/4
	when the donor has 1 and 3 usually means the engineer's xlsx is
	out of sync with the plant config — surface, don't fail.)
	"""
	issues: list[ValidationIssue] = []

	# Group by base path so we can replace the leaf folder's `tags`
	# wholesale rather than appending instance-by-instance.
	groups: dict[str, list[InstanceConfig]] = {}
	for entry in instances:
		stripped = _strip_provider(entry.base_path)
		# Drop the leading site segment — the xlsx names the site too,
		# but the donor tree already has the site root, so we navigate
		# from inside it.
		_, _, rest = stripped.partition("/")
		groups.setdefault(rest, []).append(entry.instance)

	for path, group_instances in groups.items():
		segments = [s for s in path.split("/") if s]
		if not segments:
			continue

		# Before navigating, check whether the path exists. If it
		# doesn't, that's a warning, not an error — we still create it.
		existed = _path_exists(site_root, segments)
		leaf = _navigate(site_root, segments)
		if not existed:
			issues.append(
				ValidationIssue(
					severity="warning",
					code="xlsx.path_not_in_donor",
					message=(
						f"Xlsx defined instances at /{path} but the donor tree "
						f"had no such path; the bundle now contains a newly "
						f"created folder at that location."
					),
				)
			)

		# Wipe and refill the leaf folder. This matches Designer's
		# behavior on import — the xlsx-built Pumps/Valves/Tanks fully
		# replace whatever the donor had.
		leaf["tags"] = [inst.model_dump() for inst in group_instances]

	return issues


def _path_exists(root: dict[str, Any], segments: list[str]) -> bool:
	cursor = root
	for seg in segments:
		found = None
		for child in cursor.get("tags", []):
			if child.get("name") == seg and child.get("tagType") == "Folder":
				found = child
				break
		if found is None:
			return False
		cursor = found
	return True


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def build_plant_bundle(
	plant_config: dict[str, Any],
	xlsx_bytes: bytes | None,
) -> tuple[dict[str, Any], ValidationReport, str, int]:
	"""Top-level orchestrator. Returns `(bundle, report, site, instance_count)`.

	On a validation-error path the bundle is an empty dict — the router
	is expected to surface a 400 with the report.
	"""
	errors: list[ValidationIssue] = []
	warnings: list[ValidationIssue] = []

	config_issues = _validate_plant_config(plant_config)
	if any(i.severity == "error" for i in config_issues):
		return (
			{},
			ValidationReport(errors=config_issues, warnings=[]),
			str(plant_config.get("site_long", "")),
			0,
		)
	# In practice _validate_plant_config only emits errors; capture any
	# warnings if that ever changes.
	warnings.extend(i for i in config_issues if i.severity == "warning")

	identity = build_identity_from_request(plant_config)
	cyl_cfg = plant_config["cylinders"]
	mix_cfg = plant_config["mixing"]
	cyl_count = int(cyl_cfg["count"])
	mix_count = int(mix_cfg["count"])
	cyl_map = build_renumber_map(cyl_cfg.get("numbering"), cyl_count)
	mix_map = build_renumber_map(mix_cfg.get("numbering"), mix_count)

	cyl_children, cyl_issues = _load_and_substitute(
		"cylinders", cyl_count, identity, cyl_map, mix_map
	)
	mix_children, mix_issues = _load_and_substitute(
		"mixing", mix_count, identity, cyl_map, mix_map
	)
	plant_children, plant_issues = _load_and_substitute(
		"plant_level", None, identity, cyl_map, mix_map
	)

	for batch in (cyl_issues, mix_issues, plant_issues):
		for i in batch:
			if i.severity == "error":
				errors.append(i)
			else:
				warnings.append(i)

	if errors:
		return (
			{},
			ValidationReport(errors=errors, warnings=warnings),
			identity.site_long,
			0,
		)

	site_root = _assemble_site_root(
		identity.site_long, cyl_children, mix_children, plant_children
	)

	instance_count_from_donor = _count_udt_instances(site_root)
	xlsx_instance_count = 0

	if xlsx_bytes:
		parsed = parse_workbook(xlsx_bytes)
		xlsx_instances, xlsx_report = build_all(parsed)
		# Carry over xlsx errors/warnings — they show up in the response
		# alongside donor/substitution warnings.
		for i in xlsx_report.errors:
			errors.append(i)
		for i in xlsx_report.warnings:
			warnings.append(i)
		if errors:
			return (
				{},
				ValidationReport(errors=errors, warnings=warnings),
				identity.site_long,
				0,
			)
		graft_issues = _graft_xlsx_instances(site_root, xlsx_instances)
		warnings.extend(graft_issues)
		xlsx_instance_count = len(xlsx_instances)

	# Final instance count: xlsx-built (the new ones) plus the donor's
	# pre-existing UdtInstances that weren't replaced. Easiest to just
	# recount the final tree.
	final_count = _count_udt_instances(site_root)
	# Sanity flag if final_count < xlsx_instance_count (shouldn't happen).
	if xlsx_bytes and final_count < xlsx_instance_count:
		warnings.append(
			ValidationIssue(
				severity="warning",
				code="bundle.instance_count_unexpected",
				message=(
					f"Final instance count ({final_count}) is less than the "
					f"xlsx instance count ({xlsx_instance_count}); something "
					f"in the graft step may have failed silently."
				),
			)
		)

	return (
		site_root,
		ValidationReport(errors=errors, warnings=warnings),
		identity.site_long,
		final_count,
	)


def _count_udt_instances(node: dict[str, Any]) -> int:
	"""Count `UdtInstance` tags anywhere in the tree."""
	count = 0
	if node.get("tagType") == "UdtInstance":
		count += 1
	for child in node.get("tags", []) or []:
		count += _count_udt_instances(child)
	return count


# Re-export `build_ignition_tree` for callers that want to inspect the
# packaged form independently — same helper the existing /build endpoint
# uses for its xlsx-only path.
__all__ = [
	"build_plant_bundle",
	"build_ignition_tree",
]
