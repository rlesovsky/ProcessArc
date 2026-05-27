"""Substitution engine for the Plant Bundle Builder.

Pure functions that walk a donor tree and produce a new tree with all
plant-identity placeholders replaced by real values, with OPC bracket
names defensively rewritten, and with cylinder/mix folder numbers
renumbered if the per-request mapping calls for it.

The engine is deliberately defensive: even though the committed donor
files were already scrubbed by the extraction script, the same
bracket-cleanup pass runs at substitution time. If a future donor is
edited by hand and a literal bracket name slips in, this is what
catches it.

See `backend/features/ignition_tags/scripts/extract_donor.py` for the
parallel pass that runs at extraction time. The rules deliberately
overlap.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from .schema import ValidationIssue


# Placeholder tokens — must match the set in donor.py.
PH_SITE_LONG = "__SITE_LONG__"
PH_SITE_SHORT = "__SITE_SHORT__"
PH_PLANT_NUM = "__PLANT_NUM__"
PH_REGION_CODE = "__REGION_CODE__"
PH_MQTT_TOPIC = "__MQTT_TOPIC__"
PH_MAIN_PROJECT = "__MAIN_PROJECT_NAME__"

# UDT parameter brackets that must pass through unchanged.
PARAMETER_BRACKETS = {"{plc}", "{PLC}", "m{plc}"}

# Bracket pattern — same shape as in the extraction script.
BRACKET_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_ ]{0,30})\]")


@dataclass
class PlantIdentity:
	"""The plant-identity values supplied by the request, normalized to
	strings ready for substitution.

	`plant_num` is held as a string because most occurrences are string
	substitutions. The one place that needs an int — `Plant Info/Plant
	Number` value — is detected separately by `_coerce_numeric_value`
	(based on the original donor value being a non-string placeholder
	wrapper) so that the bundle's typed JSON shape is preserved.
	"""

	site_long: str
	site_short: str
	plant_num: str
	region_code: str
	mqtt_topic: str
	main_project: str

	def as_replacements(self) -> dict[str, str]:
		"""Placeholder → real value map, ordered for deterministic substitution."""
		return {
			# Order matters: replace longer/composite placeholders first
			# so a shorter one can't accidentally chip away at the larger.
			# In practice the placeholders are distinct enough (each starts
			# with `__SITE_`, `__PLANT_`, etc.) that collisions are
			# impossible, but emitting an ordered map keeps the engine
			# explicit about it.
			PH_MAIN_PROJECT: self.main_project,
			PH_MQTT_TOPIC: self.mqtt_topic,
			PH_SITE_LONG: self.site_long,
			PH_SITE_SHORT: self.site_short,
			PH_REGION_CODE: self.region_code,
			PH_PLANT_NUM: self.plant_num,
		}


@dataclass
class _Counters:
	"""Mutable counters threaded through the substitution walk."""

	bracket_rewrites: dict[str, int] = field(default_factory=dict)
	cylinder_renames: dict[str, str] = field(default_factory=dict)
	mix_renames: dict[str, str] = field(default_factory=dict)

	def bump(self, bucket: dict[str, int], key: str) -> None:
		bucket[key] = bucket.get(key, 0) + 1


def _substitute_string(value: str, replacements: dict[str, str]) -> str:
	"""Apply placeholder substitutions to a single string in a single pass.

	The string is rebuilt by iterating the replacements map in order;
	each call to `str.replace` only acts on the literal placeholder
	token, so there is no risk of a substituted value being re-matched
	by a later rule.
	"""
	new = value
	for token, real in replacements.items():
		if token in new:
			new = new.replace(token, real)
	return new


def _rewrite_brackets(
	value: str, site_short: str, counters: _Counters
) -> str:
	"""Defensive bracket rewrite — same rule as the extraction script.

	Anything inside `[...]` that isn't `{plc}`/`{PLC}`/`m{plc}` AND
	isn't already the new plant's short name is treated as a leaked
	literal plant connection and replaced with the new plant's short
	name. Records each distinct rewritten name and its occurrence count
	so the caller can surface a warning.

	This pass runs *after* placeholder substitution, so a clean donor
	whose brackets were `[__SITE_SHORT__]` will already read
	`[<new short>]` and the check below silently no-ops. Only true leaks
	(brackets containing a *different* plant's name) get counted.
	"""

	def _replace(match: re.Match[str]) -> str:
		name = match.group(1)
		if name in PARAMETER_BRACKETS or name == site_short:
			return match.group(0)
		counters.bump(counters.bracket_rewrites, name)
		return f"[{site_short}]"

	return BRACKET_RE.sub(_replace, value)


# ---------------------------------------------------------------------------
# Renumbering
# ---------------------------------------------------------------------------


def _build_path_rewrite_re(
	branch: str, mapping: dict[int, int]
) -> re.Pattern[str] | None:
	"""Compile a regex that rewrites every reference to `<branch>/<n>/`
	in a tag-path-like string, based on the supplied number mapping.

	Branch is `"Cylinders"` or `"Mixing"`. The pattern matches strings of
	the form `Cylinders/2/` or `/Cylinders/2/...` — i.e. the folder name
	followed by a slash, a digit, and a trailing slash. The trailing
	slash anchors the match so `Cylinders/12/...` (hypothetically) would
	not be falsely matched by an entry for `Cylinders/1`.

	Returns None when the mapping is identity for every key, since
	there's no work to do.
	"""
	if not mapping or all(k == v for k, v in mapping.items()):
		return None
	# We don't compile a single substitution regex — we use a function
	# replacement instead. So just return a sentinel regex that matches
	# any `<branch>/<digit>/`.
	return re.compile(rf"(?<![A-Za-z]){re.escape(branch)}/(\d+)(?=/)")


def _renumber_string(
	value: str,
	cylinder_re: re.Pattern[str] | None,
	cylinder_map: dict[int, int],
	mixing_re: re.Pattern[str] | None,
	mixing_map: dict[int, int],
) -> str:
	"""Apply cylinder + mix renumbering to one string."""
	new = value
	if cylinder_re is not None:

		def _cyl(match: re.Match[str]) -> str:
			n = int(match.group(1))
			target = cylinder_map.get(n, n)
			return f"Cylinders/{target}"

		new = cylinder_re.sub(_cyl, new)
	if mixing_re is not None:

		def _mix(match: re.Match[str]) -> str:
			n = int(match.group(1))
			target = mixing_map.get(n, n)
			return f"Mixing/{target}"

		new = mixing_re.sub(_mix, new)
	return new


def _rename_numbered_top_tags(
	tags: list[dict[str, Any]],
	mapping: dict[int, int],
	bucket: dict[str, str],
) -> None:
	"""Rewrite the `name` field of every top-level numbered folder.

	The cylinders/mixing donors emit the numbered subfolders directly as
	the top-level `tags` list — there is no wrapping `Cylinders` or
	`Mixing` folder in the donor file (the bundle builder reconstructs
	it). So we just walk `tags` and rename any child whose name parses
	as an integer per the mapping.
	"""
	if not mapping or all(k == v for k, v in mapping.items()):
		return
	for child in tags:
		old_name = child.get("name")
		try:
			old_int = int(str(old_name))
		except ValueError:
			continue
		new_int = mapping.get(old_int)
		if new_int is None or new_int == old_int:
			continue
		child["name"] = str(new_int)
		bucket[str(old_int)] = str(new_int)


# ---------------------------------------------------------------------------
# Per-tag numeric coercion
# ---------------------------------------------------------------------------

# Tags whose `value` was stored as a placeholder string in the donor but
# whose live type should be the corresponding native value at runtime.
# Each entry is a list of path segments (rooted at the plant root, i.e.
# starting with one of the top-level folders).
_NUMERIC_PLACEHOLDER_TAGS = (
	(("Plant Info", "Plant Number"), PH_PLANT_NUM, int),
)


def _coerce_numeric_values(
	tags: list[dict[str, Any]], identity: PlantIdentity
) -> None:
	"""Walk a small known list of tag paths and convert their placeholder
	string back to its native numeric type after substitution.

	Without this, `Plant Info/Plant Number` would end up as the string
	`"532"` after substitution — but the original donor's tag holds an
	int, and Ignition's Tag Browser Import will refuse the type
	mismatch. So we look up the well-known integer paths and coerce.
	"""

	def find(node: dict[str, Any], parts: tuple[str, ...]) -> dict[str, Any] | None:
		if not parts:
			return node
		for child in node.get("tags", []) or []:
			if child.get("name") == parts[0]:
				return find(child, parts[1:])
		return None

	for path, _placeholder, kind in _NUMERIC_PLACEHOLDER_TAGS:
		top_name = path[0]
		for top in tags:
			if top.get("name") != top_name:
				continue
			target = find(top, path[1:])
			if target is None:
				continue
			value = target.get("value")
			if not isinstance(value, str):
				continue
			# After substitution, the placeholder string is now the live
			# value. Convert to the declared kind. A bad input (non-numeric
			# plant_num for an int tag) will raise — surfaced as a 400
			# elsewhere; the request validator should have caught it.
			try:
				target["value"] = kind(value)
			except ValueError:
				# Leave as string if it can't be coerced — the caller will
				# fail validation later when comparing types. We don't want
				# to silently drop the value.
				pass


# ---------------------------------------------------------------------------
# Main walk
# ---------------------------------------------------------------------------


def substitute(
	donor_tags: list[dict[str, Any]],
	*,
	identity: PlantIdentity,
	branch: str | None = None,
	cylinder_mapping: dict[int, int] | None = None,
	mix_mapping: dict[int, int] | None = None,
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
	"""Return a fresh tree with every substitution rule applied.

	`donor_tags` is mutated in place — pass a deep copy in if you need
	to keep the original intact (the donor loader already deep-copies).

	`branch` is `"cylinders"`, `"mixing"`, or `"plant_level"`. For the
	first two, the donor's top tags are the numbered folders themselves
	and the matching `*_mapping` is applied to their `name` fields.

	`cylinder_mapping` and `mix_mapping` map source folder numbers to
	target folder numbers. They are applied to *path-shaped strings* in
	every donor regardless of branch (a plant_level expression that
	references `Cylinders/2/...` still gets renumbered), and to the
	donor's own numbered top tags when `branch` matches.

	Defaults to identity (no renumbering).
	"""
	cylinder_mapping = dict(cylinder_mapping or {})
	mix_mapping = dict(mix_mapping or {})
	counters = _Counters()

	replacements = identity.as_replacements()
	cyl_re = _build_path_rewrite_re("Cylinders", cylinder_mapping)
	mix_re = _build_path_rewrite_re("Mixing", mix_mapping)

	def walk(node: Any) -> Any:
		if isinstance(node, dict):
			out: dict[str, Any] = {}
			for k, v in node.items():
				if isinstance(v, str):
					# Per-string passes, in this exact order:
					#  1. Placeholder substitution turns donor tokens
					#     (`__SITE_SHORT__` etc.) into the real values.
					#  2. Bracket rewrite, scoped to OPC item paths only,
					#     catches any leaked literal plant name that
					#     escaped the extraction pass. Already-clean
					#     brackets (now equal to the new short name) are
					#     silently passed through.
					#  3. Branch path renumbering rewrites
					#     `/Cylinders/<n>/` and `/Mixing/<n>/` references
					#     per the per-request mapping.
					new_v = _substitute_string(v, replacements)
					if _looks_like_opc_path(k):
						new_v = _rewrite_brackets(new_v, identity.site_short, counters)
					new_v = _renumber_string(new_v, cyl_re, cylinder_mapping, mix_re, mix_mapping)
					out[k] = new_v
				else:
					out[k] = walk(v)
			return out
		if isinstance(node, list):
			return [walk(item) for item in node]
		return node

	# Pass 1: substitute every string in place.
	new_tags = [walk(t) for t in donor_tags]

	# Pass 2: rename the donor's numbered top tags. Only applies when
	# this donor is the cylinders or mixing branch (plant_level has no
	# numbered top tags).
	if branch == "cylinders":
		_rename_numbered_top_tags(new_tags, cylinder_mapping, counters.cylinder_renames)
	elif branch == "mixing":
		_rename_numbered_top_tags(new_tags, mix_mapping, counters.mix_renames)

	# Pass 3: coerce known numeric placeholders back to their native type.
	_coerce_numeric_values(new_tags, identity)

	issues = _emit_warnings(counters, cylinder_mapping, mix_mapping)
	return new_tags, issues


# Field names whose contents carry an OPC item path. Bracket cleanup
# is intentionally scoped to these *only* — expressions and scripts
# legitimately reference `[SCADA]<site>/...`, `[System]Gateway/...`,
# and Ignition's `[<provider>]<tag-path>` shorthand, and we do NOT
# want to defensively rewrite those. The extraction script's
# `[SCADA]<long-name>/...` pass already cleans cross-plant leaks in
# the script/expression text.
_OPC_PATH_FIELDS = frozenset({
	"opcItemPath",  # string-form opcItemPath (e.g. on Plant Info atomic tags)
	"binding",      # inside a dict-form opcItemPath
})


def _looks_like_opc_path(field_name: str) -> bool:
	return field_name in _OPC_PATH_FIELDS


def _emit_warnings(
	counters: _Counters,
	cylinder_mapping: dict[int, int],
	mix_mapping: dict[int, int],
) -> list[ValidationIssue]:
	issues: list[ValidationIssue] = []

	if counters.bracket_rewrites:
		summary = ", ".join(
			f"[{name}]×{count}" for name, count in sorted(counters.bracket_rewrites.items())
		)
		issues.append(
			ValidationIssue(
				severity="warning",
				code="bracket.rewritten",
				message=(
					f"Defensively rewrote bracket connection names to the new plant's "
					f"short name: {summary}. (This catches leaked references in donor "
					f"strings; expected to be zero on a clean donor.)"
				),
			)
		)

	if counters.cylinder_renames:
		summary = ", ".join(
			f"{src}→{tgt}" for src, tgt in sorted(counters.cylinder_renames.items())
		)
		issues.append(
			ValidationIssue(
				severity="warning",
				code="cylinder.renumbered",
				message=f"Cylinder folders renumbered: {summary}.",
			)
		)

	if counters.mix_renames:
		summary = ", ".join(
			f"{src}→{tgt}" for src, tgt in sorted(counters.mix_renames.items())
		)
		issues.append(
			ValidationIssue(
				severity="warning",
				code="mix.renumbered",
				message=f"Mix-system folders renumbered: {summary}.",
			)
		)

	return issues


# ---------------------------------------------------------------------------
# Convenience: build identity + mapping from API request shape
# ---------------------------------------------------------------------------


def build_identity_from_request(plant_config: dict[str, Any]) -> PlantIdentity:
	"""Construct a PlantIdentity from the parsed request body.

	Applies the UFP convention defaults for `mqtt_topic` and
	`main_project` when those keys are omitted. The router's request
	validator should have already verified that the required keys are
	present.
	"""
	site_short = str(plant_config["site_short"])
	plant_num = str(plant_config["plant_number"])
	mqtt = plant_config.get("mqtt_topic") or f"UFP Industries/{plant_num}-{site_short}/PTS"
	main = plant_config.get("main_project") or f"_{plant_num}_{site_short}"
	return PlantIdentity(
		site_long=str(plant_config["site_long"]),
		site_short=site_short,
		plant_num=plant_num,
		region_code=str(plant_config["region_code"]),
		mqtt_topic=str(mqtt),
		main_project=str(main),
	)


def build_renumber_map(numbering: list[int] | None, count: int) -> dict[int, int]:
	"""Build a `donor index → target number` mapping.

	The donor's folders are numbered 1..count sequentially. The request
	may specify a target numbering like `[1, 3]` for a 2-cylinder plant
	whose cylinders are 1 and 3 rather than 1 and 2.

	Defaults to identity when `numbering` is omitted or already
	sequential.
	"""
	if not numbering:
		return {i: i for i in range(1, count + 1)}
	return {i + 1: target for i, target in enumerate(numbering)}
