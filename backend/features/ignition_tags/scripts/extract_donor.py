"""Donor extraction script for the Plant Bundle Builder.

Takes a real plant export (e.g. `Athens.json`, `tags.json` for Bartow)
and emits a donor fragment plus a sibling `.log` file documenting every
substitution that was performed.

This is the one-time work documented in Section 9 of the Plant Bundle
Builder feature design. It is run by an engineer when (a) the initial
donor library is being built, or (b) a new source plant becomes the
canonical reference for a particular branch shape.

Usage:
    python -m backend.features.ignition_tags.scripts.extract_donor \\
        --source path/to/Athens.json \\
        --branch cylinders \\
        --site-short Athens \\
        --site-long "Athens AL 527" \\
        --plant-num 527 \\
        --region-code AL \\
        --out backend/features/ignition_tags/donors/cylinders_3.json

The `--branch` flag selects which subtree to extract:
    cylinders     → root.tags["Cylinders"].tags  (a list of N numbered folders)
    mixing        → root.tags["Mixing"].tags     (a list of N numbered folders)
    plant_level   → root.tags filtered to the four plant-level folders

The output is always a JSON object of shape `{"tags": [...]}` — the
children that belong under the new site root. The bundle builder
concatenates the three selected donors' arrays under one root folder.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# The four top-level folders that make up the plant-level fragment.
# Tram is intentionally excluded — it is Bartow-specific and is not part
# of any reusable donor.
PLANT_LEVEL_FOLDERS = ("Plant Info", "Treating Data", "Offline SQL", "Production")

# Bracket names that are legitimate UDT parameter references. Anything
# else inside a [<name>] is treated as a leaked plant connection and is
# rewritten to the new plant's short name. See feature design §5.2.
PARAMETER_BRACKETS = {"{plc}", "{PLC}", "m{plc}"}

# Datasource values that are *not* the plant's own short name. Cataloged
# across the Athens and Bartow exports: 'lansing' (the historical
# central DB) and the empty string. Any other literal datasource value
# is treated as a leak (the manual cleanup missed it) and rewritten to
# the new plant's short name — same defensive principle as the bracket
# rule for OPC item paths.
DATASOURCE_CONSTANTS = {"lansing", ""}

# History provider values that are not the plant's own short name.
HISTORY_PROVIDER_CONSTANTS = {""}

# A `[SCADA]<plant-long-name>/...` source-tag-path reference. The
# long-name shape is `<word(s)> <2-letter region> <3-digit plant num>`.
# Examples this matches:
#   [SCADA]Orlando FL 439/Mixing/2/...
#   [SCADA]Rockledge FL 524/...
#   [SCADA]Fairless Hills PA 552/...
#   [SCADA]Athens AL 527/...
# Captures the long-name portion so it can be replaced with
# __SITE_LONG__ uniformly — whether it's the canonical source or a leak.
SCADA_LONG_NAME_RE = re.compile(
	r"\[SCADA\]([A-Za-z][A-Za-z0-9]*(?: [A-Za-z][A-Za-z0-9]*)*) ([A-Za-z]{2}) (\d{3})/"
)

# Placeholder tokens emitted into donor files.
PH_SITE_LONG = "__SITE_LONG__"
PH_SITE_SHORT = "__SITE_SHORT__"
PH_PLANT_NUM = "__PLANT_NUM__"
PH_REGION_CODE = "__REGION_CODE__"
PH_MQTT_TOPIC = "__MQTT_TOPIC__"
PH_MAIN_PROJECT = "__MAIN_PROJECT_NAME__"

# Bracket pattern: matches "[Name]" where Name starts with a letter and
# is followed by letters/digits/underscores/spaces. Captures the inside.
# Deliberately does *not* match brackets that wrap a JSON array literal
# (those start with a quote or digit).
BRACKET_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_ ]{0,30})\]")


@dataclass
class ExtractionContext:
	"""Plant-identity strings derived from CLI args, used as substitution targets."""

	site_long: str
	site_short: str
	plant_num: str
	region_code: str
	mqtt_topic: str
	main_project: str

	@classmethod
	def from_args(cls, args: argparse.Namespace) -> "ExtractionContext":
		# Default the MQTT topic + main project name to the UFP convention
		# when not supplied. The values shipped by Athens and Bartow both
		# follow this pattern.
		mqtt = args.mqtt_topic or f"UFP Industries/{args.plant_num}-{args.site_short}/PTS"
		main = args.main_project or f"_{args.plant_num}_{args.site_short}"
		return cls(
			site_long=args.site_long,
			site_short=args.site_short,
			plant_num=str(args.plant_num),
			region_code=args.region_code,
			mqtt_topic=mqtt,
			main_project=main,
		)


@dataclass
class ExtractionLog:
	"""Counts the rewrites this run made, keyed by category."""

	bracket_rewrites: dict[str, int] = field(default_factory=dict)
	datasource_rewrites: dict[str, int] = field(default_factory=dict)
	history_provider_rewrites: dict[str, int] = field(default_factory=dict)
	scada_long_name_rewrites: dict[str, int] = field(default_factory=dict)
	whole_value_rewrites: dict[str, int] = field(default_factory=dict)
	in_string_rewrites: dict[str, int] = field(default_factory=dict)
	plant_info_overrides: list[str] = field(default_factory=list)
	dropped_subtrees: list[str] = field(default_factory=list)
	anomalies: list[str] = field(default_factory=list)
	source: str = ""
	source_plant_long: str = ""
	branch: str = ""
	tag_counts: dict[str, int] = field(default_factory=dict)

	def bump(self, bucket: dict[str, int], key: str) -> None:
		bucket[key] = bucket.get(key, 0) + 1

	def render(self) -> str:
		out: list[str] = []
		out.append(f"Source file:        {self.source}")
		out.append(f"Source plant name:  {self.source_plant_long}")
		out.append(f"Branch extracted:   {self.branch}")
		out.append("")
		out.append("Tag counts in extracted fragment (by tagType):")
		for k in sorted(self.tag_counts):
			out.append(f"  {k}: {self.tag_counts[k]}")
		out.append("")
		out.append("Whole-value substitutions:")
		for k in sorted(self.whole_value_rewrites):
			out.append(f"  {k}: {self.whole_value_rewrites[k]}")
		out.append("")
		out.append("In-string substitutions:")
		for k in sorted(self.in_string_rewrites):
			out.append(f"  {k}: {self.in_string_rewrites[k]}")
		out.append("")
		out.append("OPC bracket rewrites (raw bracket name → __SITE_SHORT__):")
		for k in sorted(self.bracket_rewrites):
			marker = "  (canonical)" if k.lower() == self.source_plant_long.split()[0].lower() else "  (LEAK)"
			out.append(f"  [{k}]: {self.bracket_rewrites[k]}{marker}")
		out.append("")
		out.append("Datasource rewrites (raw datasource value → __SITE_SHORT__):")
		for k in sorted(self.datasource_rewrites):
			marker = "  (canonical)" if k.lower() == self.source_plant_long.split()[0].lower() else "  (LEAK)"
			out.append(f"  {k!r}: {self.datasource_rewrites[k]}{marker}")
		out.append("")
		out.append("History provider rewrites (raw value → __SITE_SHORT__):")
		for k in sorted(self.history_provider_rewrites):
			marker = "  (canonical)" if k.lower() == self.source_plant_long.split()[0].lower() else "  (LEAK)"
			out.append(f"  {k!r}: {self.history_provider_rewrites[k]}{marker}")
		out.append("")
		out.append("[SCADA]<long-name>/... rewrites (any long name → __SITE_LONG__):")
		for k in sorted(self.scada_long_name_rewrites):
			marker = "  (canonical)" if k == self.source_plant_long else "  (LEAK)"
			out.append(f"  {k!r}: {self.scada_long_name_rewrites[k]}{marker}")
		out.append("")
		out.append("Plant Info per-path value overrides:")
		for line in self.plant_info_overrides:
			out.append(f"  {line}")
		out.append("")
		out.append("Subtrees dropped during extraction:")
		for line in self.dropped_subtrees:
			out.append(f"  {line}")
		out.append("")
		out.append("Anomalies observed:")
		if not self.anomalies:
			out.append("  (none)")
		for line in self.anomalies:
			out.append(f"  {line}")
		return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Substitution primitives
# ---------------------------------------------------------------------------


def _substitute_brackets(value: str, log: ExtractionLog) -> str:
	"""Rewrite every [<name>] in `value` to [__SITE_SHORT__] unless the
	name is one of the recognized {plc} parameter forms.

	The bracket name is preserved in the log so the next maintainer can
	see what was cleaned up (canonical site name vs leak from another
	plant).
	"""

	def _replace(match: re.Match[str]) -> str:
		name = match.group(1)
		if name in PARAMETER_BRACKETS:
			return match.group(0)
		log.bump(log.bracket_rewrites, name)
		return f"[{PH_SITE_SHORT}]"

	return BRACKET_RE.sub(_replace, value)


def _substitute_compound_strings(value: str, ctx: ExtractionContext, log: ExtractionLog) -> str:
	"""Replace the longest, most specific plant-identity patterns first,
	then progressively shorter ones, so that e.g. `Athens AL 527` is
	caught as a single `__SITE_LONG__` before the bare `Athens` rule fires.

	Order matters: site_long → mqtt_topic → main_project → site_short.
	"""
	# Whole-string compound values
	for needle, token, bucket_label in (
		(ctx.site_long, PH_SITE_LONG, f"{ctx.site_long!r} → {PH_SITE_LONG}"),
		(ctx.mqtt_topic, PH_MQTT_TOPIC, f"{ctx.mqtt_topic!r} → {PH_MQTT_TOPIC}"),
		(ctx.main_project, PH_MAIN_PROJECT, f"{ctx.main_project!r} → {PH_MAIN_PROJECT}"),
	):
		if needle and needle in value:
			occurrences = value.count(needle)
			value = value.replace(needle, token)
			log.in_string_rewrites[bucket_label] = log.in_string_rewrites.get(bucket_label, 0) + occurrences

	# Short name. Only rewrite when surrounded by non-identifier chars or
	# when at the boundary of the string. Avoids matching `Athens` inside
	# `__SITE_LONG__` (the placeholder we just substituted), and avoids
	# matching `Bartow` inside a longer identifier that happens to contain
	# it as a substring.
	short = ctx.site_short
	if short:
		pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(short)}(?![A-Za-z0-9_])")
		new_value, count = pattern.subn(PH_SITE_SHORT, value)
		if count:
			label = f"{short!r} → {PH_SITE_SHORT}"
			log.in_string_rewrites[label] = log.in_string_rewrites.get(label, 0) + count
			value = new_value

	return value


def _transform_datasource(value: str, log: ExtractionLog) -> str:
	"""Rewrite a `datasource` field to __SITE_SHORT__ unless it is a known
	constant (e.g. 'lansing', empty string).

	The same defensive principle as the bracket rule: any literal plant
	name here is either the canonical source or a leak from a prior
	plant; both should become the new plant's short name.
	"""
	if value in DATASOURCE_CONSTANTS:
		return value
	log.bump(log.datasource_rewrites, value)
	return PH_SITE_SHORT


def _transform_history_provider(value: str, log: ExtractionLog) -> str:
	"""Rewrite a `historyProvider` field — same defensive logic as the
	datasource rule. Constants ('') pass through; everything else
	becomes __SITE_SHORT__.
	"""
	if value in HISTORY_PROVIDER_CONSTANTS:
		return value
	log.bump(log.history_provider_rewrites, value)
	return PH_SITE_SHORT


def _substitute_scada_long_names(value: str, log: ExtractionLog) -> str:
	"""Rewrite any `[SCADA]<plant-long-name>/...` reference to
	`[SCADA]__SITE_LONG__/...`.

	Catches both the canonical source plant and leaked references to
	other plants (Athens has `[SCADA]Rockledge FL 524/...` strings,
	Bartow has `[SCADA]Orlando FL 439/...` strings, etc.). Same
	defensive principle as the bracket rule.
	"""

	def _replace(match: re.Match[str]) -> str:
		short_part = match.group(1)
		region_part = match.group(2)
		num_part = match.group(3)
		long_name = f"{short_part} {region_part} {num_part}"
		log.bump(log.scada_long_name_rewrites, long_name)
		return f"[SCADA]{PH_SITE_LONG}/"

	return SCADA_LONG_NAME_RE.sub(_replace, value)


def _transform_string(
	value: str,
	*,
	ctx: ExtractionContext,
	log: ExtractionLog,
	apply_brackets: bool,
) -> str:
	"""Apply the standard string substitutions to one string value.

	`apply_brackets` is the caller's signal that this field contains an
	OPC item path (a string-form `opcItemPath`, or a `binding` inside a
	dict-form one). Bracket cleanup only runs on those — applying it to
	expressions or scripts would mangle their `[SCADA]...` references.
	"""
	new = value
	if apply_brackets:
		new = _substitute_brackets(new, log)
	# Catch leaked [SCADA]<other-plant-long-name>/... before the
	# compound-string pass so the leaked long name doesn't get
	# partially mangled by the short-name rule.
	new = _substitute_scada_long_names(new, log)
	new = _substitute_compound_strings(new, ctx, log)
	return new


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------


def _walk_and_substitute(node: Any, ctx: ExtractionContext, log: ExtractionLog) -> Any:
	"""Return a new tree with substitutions applied.

	Pure: does not mutate the input.

	String fields whose semantics matter for bracket cleanup are handled
	specially: a top-level `opcItemPath` (when it's a plain string) and a
	`binding` inside a dict-form `opcItemPath` both get the bracket pass.
	Every other string field gets the compound-string pass but not the
	bracket pass.
	"""
	if isinstance(node, dict):
		out: dict[str, Any] = {}
		for k, v in node.items():
			if k == "opcItemPath" and isinstance(v, str):
				out[k] = _transform_string(v, ctx=ctx, log=log, apply_brackets=True)
			elif k == "opcItemPath" and isinstance(v, dict):
				inner: dict[str, Any] = {}
				for ik, iv in v.items():
					if ik == "binding" and isinstance(iv, str):
						inner[ik] = _transform_string(iv, ctx=ctx, log=log, apply_brackets=True)
					else:
						inner[ik] = _walk_and_substitute(iv, ctx, log)
				out[k] = inner
			elif k == "datasource" and isinstance(v, str):
				out[k] = _transform_datasource(v, log)
			elif k == "historyProvider" and isinstance(v, str):
				out[k] = _transform_history_provider(v, log)
			elif isinstance(v, str):
				out[k] = _transform_string(v, ctx=ctx, log=log, apply_brackets=False)
			else:
				out[k] = _walk_and_substitute(v, ctx, log)
		return out
	if isinstance(node, list):
		return [_walk_and_substitute(item, ctx, log) for item in node]
	return node


# ---------------------------------------------------------------------------
# Plant Info per-tag overrides
# ---------------------------------------------------------------------------


# Map of `<folder-path>/<tag-name>` → (field, placeholder, type). The
# walker visits Plant Info after the generic substitution pass; these
# overrides ensure the per-tag values land on the right placeholder even
# when the source value didn't match a compound-string pattern.
#
# Example: `Plant Info/RegionNumber` has `datasource: "Athens"` but no
# `value` field — the compound-string rule already rewrites the
# `datasource` because Athens is the short name, so this map mostly
# serves as a record of expected overrides for the log.
PLANT_INFO_OVERRIDES = {
	"Plant Info/Plant Number": ("value", PH_PLANT_NUM),
	"Plant Info/DB Name": ("value", PH_SITE_SHORT),
	"Plant Info/Plant MQTT Topic": ("value", PH_MQTT_TOPIC),
	"Plant Info/Named Query Info/Main Project Name": ("value", PH_MAIN_PROJECT),
	"Plant Info/RegionNumber": ("datasource", PH_SITE_SHORT),
	"Plant Info/CustomerNumber": ("datasource", PH_SITE_SHORT),
}


def _apply_plant_info_overrides(tags: list[dict[str, Any]], log: ExtractionLog) -> None:
	"""Write the placeholder into the known per-tag fields, in-place.

	Most of these are no-ops because the generic substitution pass
	already replaced the literal short name. But Plant Number is an
	integer in the source and needs the placeholder string written
	explicitly here (a numeric field can't be string-substituted).
	"""

	def walk(node: dict[str, Any], prefix: str) -> None:
		here = f"{prefix}/{node.get('name')}" if prefix else node.get("name", "")
		key = here.lstrip("/")
		override = PLANT_INFO_OVERRIDES.get(key)
		if override is not None:
			field_name, placeholder = override
			old = node.get(field_name)
			if old != placeholder:
				node[field_name] = placeholder
				log.plant_info_overrides.append(
					f"{key}.{field_name}: {old!r} → {placeholder!r}"
				)
		for child in node.get("tags", []) or []:
			walk(child, here)

	for top in tags:
		if top.get("name") == "Plant Info":
			walk(top, "")


# ---------------------------------------------------------------------------
# Branch selection
# ---------------------------------------------------------------------------


def _select_branch(root: dict[str, Any], branch: str, log: ExtractionLog) -> list[dict[str, Any]]:
	"""Pull the subtree(s) that make up the requested donor branch."""
	top_tags = root.get("tags", []) or []

	if branch == "cylinders":
		node = next((t for t in top_tags if t.get("name") == "Cylinders"), None)
		if node is None:
			raise SystemExit("Source has no top-level 'Cylinders' folder.")
		return [node]

	if branch == "mixing":
		node = next((t for t in top_tags if t.get("name") == "Mixing"), None)
		if node is None:
			raise SystemExit("Source has no top-level 'Mixing' folder.")
		return [node]

	if branch == "plant_level":
		out: list[dict[str, Any]] = []
		seen = set()
		for wanted in PLANT_LEVEL_FOLDERS:
			node = next((t for t in top_tags if t.get("name") == wanted), None)
			if node is not None:
				out.append(node)
				seen.add(wanted)
			else:
				log.anomalies.append(
					f"Expected plant-level folder {wanted!r} missing from source."
				)
		# Note any top-level folders we deliberately dropped.
		for t in top_tags:
			name = t.get("name")
			if name not in PLANT_LEVEL_FOLDERS and name not in ("Cylinders", "Mixing"):
				log.dropped_subtrees.append(
					f"Top-level folder {name!r} dropped (not part of any donor branch)."
				)
		return out

	raise SystemExit(f"Unknown branch: {branch!r}")


# ---------------------------------------------------------------------------
# Tag-type accounting
# ---------------------------------------------------------------------------


def _count_tag_types(tags: list[dict[str, Any]], counts: dict[str, int]) -> None:
	for t in tags:
		tt = t.get("tagType", "?")
		counts[tt] = counts.get(tt, 0) + 1
		_count_tag_types(t.get("tags", []) or [], counts)


# ---------------------------------------------------------------------------
# Top-level extraction
# ---------------------------------------------------------------------------


def extract(source_path: Path, branch: str, ctx: ExtractionContext) -> tuple[dict[str, Any], ExtractionLog]:
	with source_path.open("r", encoding="utf-8") as f:
		root = json.load(f)

	log = ExtractionLog(
		source=str(source_path),
		source_plant_long=root.get("name", "<unknown>"),
		branch=branch,
	)

	# Validate sanity: the source plant's short name should appear as the
	# leading word of its long name. Use that to detect a mismatched CLI
	# input early.
	expected_short = log.source_plant_long.split()[0] if log.source_plant_long else ""
	if expected_short and expected_short != ctx.site_short:
		log.anomalies.append(
			f"Source plant short name appears to be {expected_short!r} "
			f"but --site-short was {ctx.site_short!r}."
		)

	subtrees = _select_branch(root, branch, log)
	substituted = [_walk_and_substitute(t, ctx, log) for t in subtrees]

	# Plant Info overrides apply only to the plant_level donor.
	if branch == "plant_level":
		_apply_plant_info_overrides(substituted, log)

	_count_tag_types(substituted, log.tag_counts)

	# For cylinders/mixing donors, the "tags" array we emit is the list
	# of N numbered children (1, 2, 3) — not the wrapping "Cylinders"/
	# "Mixing" folder itself, which the bundle builder reconstructs.
	# For plant_level, the emitted array is the list of top-level
	# plant-level folders directly.
	if branch in ("cylinders", "mixing"):
		# substituted has exactly one element (the "Cylinders" or "Mixing"
		# folder). Pull its `tags` list and emit those numbered subfolders.
		fragment_tags = substituted[0].get("tags", []) or []
	else:
		fragment_tags = substituted

	# Sanity check: no leftover literals of source plant should remain.
	leftover = _scan_for_leftovers(fragment_tags, ctx)
	for line in leftover:
		log.anomalies.append(line)

	donor = {
		"branch": branch,
		"count": len(fragment_tags) if branch in ("cylinders", "mixing") else None,
		"tags": fragment_tags,
	}
	return donor, log


def _scan_for_leftovers(tags: list[dict[str, Any]], ctx: ExtractionContext) -> list[str]:
	"""Find lingering literals of plant-identity strings after substitution.

	Surfaced as anomalies in the log — they don't fail the extraction but
	they tell the maintainer that something escaped the substitution pass
	and should be cleaned up before committing.
	"""
	# Strings to flag. The short name is excluded because UFP terminology
	# uses some short names (like 'Tram') as common nouns in other
	# contexts; the bracket pass would have caught the dangerous cases.
	needles = (ctx.site_long, ctx.mqtt_topic, ctx.main_project)
	hits: dict[str, int] = {}

	def walk(node: Any) -> None:
		if isinstance(node, dict):
			for v in node.values():
				walk(v)
		elif isinstance(node, list):
			for v in node:
				walk(v)
		elif isinstance(node, str):
			for needle in needles:
				if needle and needle in node:
					hits[needle] = hits.get(needle, 0) + 1

	for t in tags:
		walk(t)

	return [f"Leftover literal {k!r} appears {v}× after substitution." for k, v in hits.items()]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Extract a donor fragment from a real plant export.")
	parser.add_argument("--source", required=True, type=Path, help="Path to the source plant JSON.")
	parser.add_argument(
		"--branch",
		required=True,
		choices=("cylinders", "mixing", "plant_level"),
		help="Which subtree to extract.",
	)
	parser.add_argument("--site-short", required=True, help="Source plant short name (e.g. 'Athens').")
	parser.add_argument("--site-long", required=True, help="Source plant long name (e.g. 'Athens AL 527').")
	parser.add_argument("--plant-num", required=True, help="Source plant number (e.g. '527').")
	parser.add_argument("--region-code", required=True, help="Source plant two-letter region code (e.g. 'AL').")
	parser.add_argument("--mqtt-topic", default=None, help="Override the auto-derived MQTT topic.")
	parser.add_argument("--main-project", default=None, help="Override the auto-derived main project name.")
	parser.add_argument("--out", required=True, type=Path, help="Path to write the donor JSON.")

	args = parser.parse_args(argv)
	ctx = ExtractionContext.from_args(args)

	if not args.source.exists():
		print(f"Source not found: {args.source}", file=sys.stderr)
		return 2

	donor, log = extract(args.source, args.branch, ctx)

	args.out.parent.mkdir(parents=True, exist_ok=True)
	with args.out.open("w", encoding="utf-8") as f:
		json.dump(donor, f, indent="\t", ensure_ascii=False)
		f.write("\n")

	log_path = args.out.with_suffix(args.out.suffix + ".log")
	with log_path.open("w", encoding="utf-8") as f:
		f.write(log.render())

	print(f"Wrote {args.out} ({sum(log.tag_counts.values())} tags total)")
	print(f"Wrote {log_path}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
