"""Build the Ignition-importable folder tree.

The reference Jython called `system.tag.configure(base_path, instance, "o")`
once per UDT instance, which Ignition's runtime accepted in a minimal
form. The Tag Browser **Import** dialog, on the other hand, expects the
same format `system.tag.exportTags` produces: a single nested folder
tree rooted at the site name, with explicit `tagType` on every leaf and
folder.

This module converts the flat `(base_path, instance)` list the builder
produces into that nested tree.

Base path format from the builder:
    [<provider>]<site>/<sys_name>/<sys_num>/<folder>

Tree shape Ignition imports:
    <site>            (Folder, root)
      └── <sys_name>  (Folder)
            └── <sys_num>  (Folder)
                  └── <folder segments…>  (Folder, possibly nested if folder
                                            contains "/")
                        └── <instance>     (UdtInstance)

The `[<provider>]` prefix is *dropped* — at import time Designer asks
which tag provider to import the tree into, so the provider doesn't
belong in the file.
"""

from __future__ import annotations

import re
from typing import Any

from .schema import InstanceWithPath

# Matches "[<provider>]<rest>" at the start of a base path.
_BASE_PATH_RE = re.compile(r"^\[(?P<provider>[^\]]+)\](?P<rest>.*)$")


def _path_segments(base_path: str) -> list[str]:
	"""Split a base path into ordered folder segments, dropping `[provider]`.

	`[SCADA]Bartow FL 523/Mixing/3/Edge/Pumps` →
	    ["Bartow FL 523", "Mixing", "3", "Edge", "Pumps"]

	The folder portion (last component of the workbook's C3 cell) may
	itself contain `/` to express nested folders (e.g. `Edge/Pumps`);
	splitting the whole rest by `/` handles that uniformly.
	"""
	m = _BASE_PATH_RE.match(base_path)
	rest = m.group("rest") if m else base_path
	# Strip a leading slash if one slipped in.
	rest = rest.lstrip("/")
	return [seg for seg in rest.split("/") if seg]


def _ensure_folder(parent_tags: list[dict[str, Any]], name: str) -> dict[str, Any]:
	"""Find-or-create a Folder child named `name` under `parent_tags`."""
	for child in parent_tags:
		if child.get("name") == name and child.get("tagType") == "Folder":
			return child
	folder: dict[str, Any] = {"name": name, "tagType": "Folder", "tags": []}
	parent_tags.append(folder)
	return folder


def sort_tree(node: dict[str, Any]) -> dict[str, Any]:
	"""Deterministic-sort a tree's `tags` lists by `name`, recursively.

	Used by the golden test so output is comparable regardless of source
	workbook ordering. Returns a new dict; does not mutate `node`.
	"""
	out = dict(node)
	if "tags" in out and isinstance(out["tags"], list):
		sorted_children = sorted(
			(sort_tree(c) for c in out["tags"]),
			key=lambda c: (c.get("name", ""), c.get("tagType", "")),
		)
		out["tags"] = sorted_children
	return out


def build_ignition_tree(instances: list[InstanceWithPath]) -> dict[str, Any]:
	"""Return a single nested folder tree suitable for Ignition import.

	If `instances` is empty, returns an empty root folder named "" — the
	caller (router) can decide whether to surface that as an error.

	If the instances span multiple sites (different leading segment after
	the `[provider]` prefix), they are merged under a wrapper folder
	named "" — but in practice every workbook produces exactly one site
	per Sheet 0's C3, so this fallback rarely triggers.
	"""
	# Collect all (segments, instance) pairs first so we can pick the
	# root name from the first non-empty path. Most workbooks have one
	# site value across every sheet.
	if not instances:
		return {"name": "", "tagType": "Folder", "tags": []}

	# All instances share the same site segment in well-formed input.
	# Use the first as the root name; warn-via-merge if any disagree.
	first_segments = _path_segments(instances[0].base_path)
	root_name = first_segments[0] if first_segments else ""
	root: dict[str, Any] = {"name": root_name, "tagType": "Folder", "tags": []}

	for entry in instances:
		segments = _path_segments(entry.base_path)
		if not segments:
			# Malformed base path; attach instance directly at root.
			root["tags"].append(entry.instance.model_dump())
			continue
		# If a stray instance has a different site segment, route it
		# under that site name inside the same root tree. The frontend
		# will still render it correctly as a sibling of root_name.
		cursor_tags = root["tags"]
		if segments[0] != root_name:
			site_folder = _ensure_folder(cursor_tags, segments[0])
			cursor_tags = site_folder["tags"]
		# Walk the remaining segments, creating folders as needed.
		for segment in segments[1:]:
			folder = _ensure_folder(cursor_tags, segment)
			cursor_tags = folder["tags"]
		cursor_tags.append(entry.instance.model_dump())

	return root
