"""Donor library loader for the Plant Bundle Builder.

Loads the committed JSON fragments under `donors/` (the orthogonal
branch shapes: cylinders_N, mixing_N, plant_level) and exposes them as
plain dicts ready for the substitution engine.

The donor files are produced once by `scripts/extract_donor.py` and
checked into the repo. This module never modifies the files — it just
reads, validates, and hands out deep copies so callers can mutate
freely.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .schema import ValidationIssue


DONORS_DIR = Path(__file__).parent / "donors"

# Placeholder tokens the donor files may legitimately contain. Any
# `__SOMETHING__` token in a donor that is NOT in this set means the
# donor was edited incorrectly (e.g. a typo, an extraction-script bug).
# The loader surfaces that as an error so a malformed donor can never
# silently produce a bundle with unsubstituted placeholders.
RECOGNIZED_PLACEHOLDERS = {
	"__SITE_LONG__",
	"__SITE_SHORT__",
	"__PLANT_NUM__",
	"__REGION_CODE__",
	"__MQTT_TOPIC__",
	"__MAIN_PROJECT_NAME__",
}

# Matches any double-underscore token in a string value. Used to scan
# donors for unrecognized placeholders.
PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")


def _branch_filename(branch: str, count: int | None) -> str:
	if branch == "plant_level":
		return "plant_level.json"
	if branch in ("cylinders", "mixing"):
		if count is None:
			raise ValueError(f"`count` is required for branch={branch!r}")
		return f"{branch}_{count}.json"
	raise ValueError(f"Unknown branch: {branch!r}")


def _walk_strings(node: Any) -> list[str]:
	"""Yield every string-valued leaf in `node`. Used for placeholder scanning."""
	out: list[str] = []

	def visit(n: Any) -> None:
		if isinstance(n, dict):
			for v in n.values():
				visit(v)
		elif isinstance(n, list):
			for v in n:
				visit(v)
		elif isinstance(n, str):
			out.append(n)

	visit(node)
	return out


def _validate_placeholders(tags: list[dict[str, Any]], filename: str) -> list[ValidationIssue]:
	"""Scan a loaded donor for any `__FOO__` tokens that aren't recognized.

	Returns a list of errors — empty if every placeholder seen is one of
	the recognized tokens.
	"""
	issues: list[ValidationIssue] = []
	seen: set[str] = set()
	for s in _walk_strings(tags):
		for match in PLACEHOLDER_RE.findall(s):
			if match in RECOGNIZED_PLACEHOLDERS:
				continue
			if match in seen:
				continue
			seen.add(match)
			issues.append(
				ValidationIssue(
					severity="error",
					code="donor.placeholder_unsubstituted",
					message=(
						f"Donor {filename} contains unrecognized placeholder token "
						f"{match!r}. The donor file may have been edited incorrectly; "
						f"re-run extract_donor.py or fix the token by hand."
					),
				)
			)
	return issues


def load_donor(
	branch: str, count: int | None = None
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
	"""Load a donor fragment by `(branch, count)`.

	Returns `(tags, issues)` — the list of children that belong under the
	new site's root folder, plus any validation issues discovered while
	loading. Errors mean the donor must not be used; warnings are
	informational only.

	Raises `FileNotFoundError` if the requested donor does not exist on
	disk — the caller (plant_builder) converts that into a structured
	`donor.not_available` error.
	"""
	filename = _branch_filename(branch, count)
	path = DONORS_DIR / filename
	if not path.exists():
		raise FileNotFoundError(
			f"Donor not found: {path}. "
			f"For branch={branch!r}, count={count!r}, expected file at this path."
		)

	with path.open("r", encoding="utf-8") as f:
		raw = json.load(f)

	# Donor files are objects of shape `{"branch": ..., "count": ..., "tags": [...]}`.
	tags = raw.get("tags")
	if not isinstance(tags, list):
		return [], [
			ValidationIssue(
				severity="error",
				code="donor.malformed",
				message=f"Donor {filename}: top-level `tags` field must be a list.",
			)
		]

	issues = _validate_placeholders(tags, filename)

	# Deep-copy so callers can mutate the returned tree without affecting
	# a future load_donor() call. (The donor JSON is small enough that
	# the copy cost is negligible compared to the substitution pass.)
	return copy.deepcopy(tags), issues
