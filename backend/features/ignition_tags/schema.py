"""Pydantic models for the Ignition Tag Builder output contract.

These models intentionally mirror — exactly — the dict shape that the
reference Jython script writes via `system.tag.configure`. They use
`extra='forbid'` so that an accidental key addition in the builder
fails the test rather than silently changing the contract with Ignition.

Schema reference: docs/ignition_tag_template_spec.md (the "Output JSON
shape (the contract)" section).
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict


class OpcItemPath(BaseModel):
	model_config = ConfigDict(extra="forbid")

	bindType: Literal["parameter"]
	binding: str


class AtomicTag(BaseModel):
	"""A leaf tag inside a UDT instance.

	Carries the explicit `tagType: "AtomicTag"` discriminator because
	Ignition Designer's Tag Browser Import expects every leaf to be
	tagged. (The reference Jython only ever called `system.tag.configure`
	which accepts the minimal form, but the import path is stricter.)
	"""

	model_config = ConfigDict(extra="forbid")

	name: str
	tagType: Literal["AtomicTag"] = "AtomicTag"
	opcItemPath: OpcItemPath


class FolderTag(BaseModel):
	"""A nested folder inside a UDT instance.

	Created from dot-notation in a tag column header
	(e.g. `Status.Running` → folder `Status` containing tag `Running`).
	"""

	model_config = ConfigDict(extra="forbid")

	name: str
	tagType: Literal["Folder"]
	tags: list["AnyTag"]


AnyTag = Union[AtomicTag, FolderTag]


class InstanceConfig(BaseModel):
	"""A single UDT instance config — one per data row in the workbook.

	Structurally identical to the dict passed to
	`system.tag.configure(base_path, tag_config, "o")` in the reference
	Jython.
	"""

	model_config = ConfigDict(extra="forbid")

	name: str
	typeId: str
	tagType: Literal["UdtInstance"]
	tags: list[AnyTag]


# Pydantic v2 needs an explicit rebuild for the forward reference inside
# FolderTag.tags before validation is used.
FolderTag.model_rebuild()


class ValidationIssue(BaseModel):
	"""A single warning or error captured during parse + build."""

	severity: Literal["error", "warning"]
	code: str
	message: str
	sheet: str | None = None
	row: int | None = None  # 1-indexed spreadsheet row, for the user
	column: str | None = None


class ValidationReport(BaseModel):
	"""The validation report bundled into the output zip (or returned on 400)."""

	errors: list[ValidationIssue]
	warnings: list[ValidationIssue]

	@property
	def has_errors(self) -> bool:
		return len(self.errors) > 0


class InstanceWithPath(BaseModel):
	"""Builder output: one UDT instance plus the Ignition base path it lives at."""

	base_path: str
	source_sheet: str
	source_row: int  # 1-indexed spreadsheet row, for traceability
	instance: InstanceConfig
