"""Prose Extractor (Plan §8) — pluggable device extraction from sequence prose.

Stage 2 of the pipeline. The cylinder and mix sequencing sheets are running
English; device names live inside sentences, not columns. This module sends
that prose to the Claude API and parses a structured device list back.

Design (Plan §8.4): extraction sits behind a fixed interface — `ProseExtractor`.
The `ClaudeProseExtractor` is the Phase 1 implementation. A future P&ID extractor
(Plan §15) becomes another implementation behind the same interface, so nothing
downstream of this module knows or cares that prose was the source.

Contract notes carried from the Plan:
  - §8.2  Each sheet is extracted with the System and System Number for *that*
          sheet, taken from the Plant Configuration — never assumed.
  - §8.3  An API failure must surface as a clear error. The extractor must
          NEVER silently return an empty device list on a failed call. This is
          enforced here by raising `ProseExtractionError` — callers cannot
          mistake a failure for "no devices found".
  - §6    Output is `DeviceRecord`s — source-agnostic, carrying the real
          System Number and `SourceType.SEQUENCE_PROSE`.
  - §13 Q6 The Claude API key + UFP data-policy sign-off gates running *real*
          UFP prose. This module is policy-neutral; it extracts whatever prose
          it is given. The gate lives with the caller / engineer.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from backend.ingest import IngestedSheet
from backend.model.device import (
	Confidence,
	DeviceClass,
	DeviceRecord,
	SourceType,
	SystemKind,
)
from backend.settings import get_settings


# =============================================================================
# Errors
# =============================================================================
class ProseExtractionError(RuntimeError):
	"""Raised when prose extraction cannot complete.

	Deliberately a hard failure (Plan §8.3): a caller seeing this exception
	knows extraction did not happen. It must never be conflated with a
	successful run that found zero devices.
	"""


# =============================================================================
# What a sheet looks like to the extractor
# =============================================================================
@dataclass
class ProseSource:
	"""One unit of prose to extract, plus the system context it belongs to.

	`system` / `system_number` come from the Plant Configuration (Plan §8.2),
	NOT from the prose itself. The extractor stamps every device it finds in
	this source with this context.
	"""

	sheet_name: str
	system: SystemKind
	system_number: Optional[int]
	lines: list[str]

	@property
	def text(self) -> str:
		return "\n".join(self.lines)

	@property
	def is_empty(self) -> bool:
		return not any(ln.strip() for ln in self.lines)

	@classmethod
	def from_ingested_sheet(
		cls,
		sheet: IngestedSheet,
		system: SystemKind,
		system_number: Optional[int],
	) -> "ProseSource":
		"""Build a ProseSource from an ingested sheet.

		The caller supplies `system` / `system_number` from the Plant
		Configuration — this constructor does not infer them.
		"""
		return cls(
			sheet_name=sheet.name,
			system=system,
			system_number=system_number,
			lines=sheet.text_lines(),
		)


# =============================================================================
# What the extractor returns
# =============================================================================
@dataclass
class SheetExtraction:
	"""Result of extracting one ProseSource."""

	sheet_name: str
	system: SystemKind
	system_number: Optional[int]
	devices: list[DeviceRecord] = field(default_factory=list)
	notes: list[str] = field(default_factory=list)


@dataclass
class ProseExtractionResult:
	"""Aggregate result over every sheet handed to the extractor."""

	sheets: list[SheetExtraction] = field(default_factory=list)

	@property
	def devices(self) -> list[DeviceRecord]:
		out: list[DeviceRecord] = []
		for s in self.sheets:
			out.extend(s.devices)
		return out

	@property
	def device_count(self) -> int:
		return sum(len(s.devices) for s in self.sheets)

	def needs_review(self) -> list[DeviceRecord]:
		return [d for d in self.devices if d.confidence == Confidence.NEEDS_REVIEW]


# =============================================================================
# The pluggable interface (Plan §8.4)
# =============================================================================
class ProseExtractor(ABC):
	"""Fixed interface for prose -> device extraction.

	Phase 1 has exactly one implementation, `ClaudeProseExtractor`. A future
	P&ID extractor (Plan §15) implements this same interface. Downstream code
	depends only on `ProseExtractor`, never on a concrete class.
	"""

	@abstractmethod
	def extract_sheet(self, source: ProseSource) -> SheetExtraction:
		"""Extract devices from a single prose source.

		Implementations MUST raise `ProseExtractionError` on failure rather
		than returning an empty `SheetExtraction` (Plan §8.3).
		"""
		raise NotImplementedError

	def extract_all(self, sources: list[ProseSource]) -> ProseExtractionResult:
		"""Extract every source. Default impl loops `extract_sheet`.

		If any sheet fails, the whole call fails — a partial device list that
		looks complete is worse than a clear error (Plan §8.3).
		"""
		result = ProseExtractionResult()
		for src in sources:
			result.sheets.append(self.extract_sheet(src))
		return result


# =============================================================================
# Claude API implementation (Plan §8.2)
# =============================================================================

# Device-class vocabulary handed to the model. Mirrors model/device.py exactly;
# the model must choose from this closed set so parsing is total.
_DEVICE_CLASS_GUIDE = """\
Device classes (choose exactly one per device):
  - "Pump"          : a fixed-speed pump.
  - "VFD Pump"      : a pump under variable-frequency speed control. Pressure
                      and Strip pumps are VFD Pumps when the sequence mentions
                      speed, frequency, ramp, or VFD control.
  - "Valve"         : an on/off (open/close) valve.
  - "Control Valve" : a modulating valve driven to a setpoint/position.
  - "Tank"          : a vessel. Tanks normally come from the Chemical and Tank
                      tables, not prose — only return a Tank from prose if the
                      sequence clearly names one not in those tables."""

_SYSTEM_PROMPT = """\
You are a controls-engineering extraction assistant for wood-treatment SCADA \
projects. You read one sequence-of-operations sheet written in running English \
and identify every physical field device it names: pumps, valves, control \
valves, and (rarely) tanks.

You will be told the System and System Number this sheet belongs to. Do not \
infer or change them — every device you return belongs to that system.

Rules:
- Identify each DISTINCT physical device once, even if the prose mentions it \
many times. Merge repeated mentions into one device.
- The "base_name" is the short identifier the sequence uses for the device \
(e.g. "V9", "P1", "VPD", "Tnkv1"). Use the sheet's own wording verbatim — do \
not normalize, expand, or re-case it. Different cylinders legitimately name \
the same function differently; never rename to match another cylinder.
- "description" is a short human-readable function ("Pressure pump discharge \
valve"). If the prose does not make the function clear, give your best short \
description and lower the confidence.
- "confidence" is "High" only when the device identity and class are \
unambiguous from the prose. Use "Needs Review" whenever the name is unclear, \
the class is a judgement call, or the mention might be a process step rather \
than a device.
- "source_reference" is a short pointer to where in the sheet the device \
appears (e.g. a step name or phrase). Keep it under ~12 words.
- Do NOT invent devices that are not in the prose. Missing a device is \
recoverable at human review; a fabricated device is not.
- A pump/valve number with no clear physical referent, generic mentions of \
"the system", setpoints, timers, and alarms are NOT devices.

{device_class_guide}

Return ONLY a JSON object, no prose around it, no markdown fences:
{{
  "devices": [
    {{
      "base_name": "string",
      "device_class": "Pump | VFD Pump | Valve | Control Valve | Tank",
      "description": "string",
      "confidence": "High | Needs Review",
      "source_reference": "string"
    }}
  ]
}}
If the sheet names no devices, return {{"devices": []}}."""

_USER_PROMPT = """\
System: {system}
System Number: {system_number}
Sheet name: {sheet_name}

Sequence prose follows between the markers. Extract every field device.

<<<SEQUENCE_PROSE
{prose}
SEQUENCE_PROSE>>>"""

# Map the model's JSON string -> the DeviceClass enum. Closed set; anything
# else is treated as an unparseable device and flagged for review.
_CLASS_LOOKUP = {dc.value.lower(): dc for dc in DeviceClass}

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fences(text: str) -> str:
	"""Defensively remove ```json fences if the model adds them anyway."""
	return _FENCE_RE.sub("", text.strip())


def _coerce_class(raw: str) -> tuple[DeviceClass, bool]:
	"""Map a raw class string to DeviceClass.

	Returns (class, ok). On an unknown value, defaults to Valve and ok=False so
	the caller can drop the device's confidence to Needs Review.
	"""
	dc = _CLASS_LOOKUP.get((raw or "").strip().lower())
	if dc is None:
		return DeviceClass.VALVE, False
	return dc, True


def _coerce_confidence(raw: str) -> Confidence:
	return (
		Confidence.HIGH
		if (raw or "").strip().lower() == "high"
		else Confidence.NEEDS_REVIEW
	)


def _canonical_id(system: SystemKind, system_number: Optional[int], base_name: str) -> str:
	"""Build the Canonical ID (Plan §6.1), e.g. CYL3_VALVE_VPD / MIX1_PUMP_P1.

	Device-class is intentionally NOT in the ID — a base name is unique within
	a system, and class can be corrected at review without breaking the ID.
	"""
	sys_tag = "CYL" if system == SystemKind.CYLINDERS else "MIX"
	num = str(system_number) if system_number is not None else "X"
	clean = re.sub(r"[^A-Za-z0-9]+", "", base_name).upper() or "UNNAMED"
	return f"{sys_tag}{num}_{clean}"


class ClaudeProseExtractor(ProseExtractor):
	"""Phase 1 prose extractor — calls the Claude API (Plan §8.2).

	The API key and model come from `backend/settings`. The key is read at call
	time, so a key saved through the settings UI (which calls `reload_settings`)
	is picked up without recreating this object.
	"""

	# Per-API-call timeout. A cylinder-prose extraction usually completes well
	# under 30s; 60s is a generous ceiling that still trips a stuck connection
	# before the engineer thinks the screen is hung. Without this, a hung
	# socket leaves the task RUNNING until the server restarts.
	_DEFAULT_TIMEOUT_S = 60.0

	def __init__(
		self,
		model: Optional[str] = None,
		max_tokens: int = 4096,
		client: Optional[object] = None,
		timeout_s: Optional[float] = None,
	) -> None:
		# `client` is injectable so tests can pass a fake without a network call
		# or a real key. Production passes nothing and a real client is built.
		self._injected_client = client
		self._model_override = model
		self._max_tokens = max_tokens
		self._timeout_s = self._DEFAULT_TIMEOUT_S if timeout_s is None else timeout_s

	# -- internals ------------------------------------------------------------
	def _build_client(self):
		if self._injected_client is not None:
			return self._injected_client

		settings = get_settings()
		if not settings.has_api_key:
			raise ProseExtractionError(
				"No Anthropic API key configured. Save a key in Settings "
				"before running prose extraction."
			)
		try:
			import anthropic
		except ImportError as exc:  # pragma: no cover - dependency is pinned
			raise ProseExtractionError(
				"The 'anthropic' package is not installed in the backend env."
			) from exc
		return anthropic.Anthropic(api_key=settings.anthropic_api_key)

	def _model_name(self) -> str:
		if self._model_override:
			return self._model_override
		return get_settings().claude_model

	def _wrap_api_error(self, exc: Exception, sheet_name: str) -> ProseExtractionError:
		"""Map an anthropic SDK exception to a ProseExtractionError with a
		message the engineer can act on.

		Imports are deferred and guarded so the wrapping degrades to the
		generic "Claude API call failed" message if anthropic's error
		hierarchy is unavailable (e.g. in tests that pass a fake client
		raising a plain RuntimeError).
		"""
		try:
			import anthropic
		except ImportError:
			return ProseExtractionError(
				f"Claude API call failed for sheet '{sheet_name}': {exc}"
			)

		if isinstance(exc, anthropic.AuthenticationError):
			return ProseExtractionError(
				f"Claude API rejected the API key while extracting "
				f"'{sheet_name}'. Open Settings and save a valid key."
			)
		if isinstance(exc, anthropic.PermissionDeniedError):
			return ProseExtractionError(
				f"Claude API denied access while extracting '{sheet_name}'. "
				f"The configured key does not permit this model."
			)
		if isinstance(exc, anthropic.RateLimitError):
			return ProseExtractionError(
				f"Claude API is rate limited on '{sheet_name}'. Wait a moment, "
				f"then retry the failed row."
			)
		if isinstance(exc, anthropic.APITimeoutError):
			return ProseExtractionError(
				f"Claude API timed out while extracting '{sheet_name}' "
				f"(>{self._timeout_s:.0f}s). Retry the failed row."
			)
		if isinstance(exc, anthropic.APIConnectionError):
			return ProseExtractionError(
				f"Could not reach the Claude API while extracting "
				f"'{sheet_name}'. Check your network and retry."
			)
		if isinstance(exc, anthropic.BadRequestError):
			return ProseExtractionError(
				f"Claude API rejected the request for '{sheet_name}': {exc}. "
				f"This usually means an invalid model name in Settings."
			)
		if isinstance(exc, anthropic.APIStatusError):
			return ProseExtractionError(
				f"Claude API returned an error for '{sheet_name}': {exc}."
			)
		# Anything else (e.g. plain RuntimeError from a test fake) keeps the
		# original phrasing so existing tests continue to match on it.
		return ProseExtractionError(
			f"Claude API call failed for sheet '{sheet_name}': {exc}"
		)

	def _call_api(self, source: ProseSource) -> str:
		"""Make the API call. Returns the raw text block.

		Any failure — auth, rate limit, network, timeout, empty response — is
		converted to ProseExtractionError (Plan §8.3). Different failure modes
		get distinct, actionable messages so the Extract screen can guide the
		engineer ("check your key" vs. "rate limited" vs. "network" vs.
		"timed out") instead of dumping the raw exception.
		"""
		client = self._build_client()
		system_prompt = _SYSTEM_PROMPT.format(device_class_guide=_DEVICE_CLASS_GUIDE)
		user_prompt = _USER_PROMPT.format(
			system=source.system.value,
			system_number=source.system_number
			if source.system_number is not None
			else "(unnumbered)",
			sheet_name=source.sheet_name,
			prose=source.text,
		)

		try:
			response = client.messages.create(
				model=self._model_name(),
				max_tokens=self._max_tokens,
				system=system_prompt,
				messages=[{"role": "user", "content": user_prompt}],
				timeout=self._timeout_s,
			)
		except Exception as exc:
			raise self._wrap_api_error(exc, source.sheet_name) from exc

		text_parts = [
			block.text
			for block in getattr(response, "content", [])
			if getattr(block, "type", None) == "text"
		]
		if not text_parts:
			raise ProseExtractionError(
				f"Claude API returned no text content for sheet "
				f"'{source.sheet_name}'."
			)
		return "".join(text_parts)

	def _parse(self, raw_text: str, source: ProseSource) -> SheetExtraction:
		"""Parse the model's JSON into DeviceRecords stamped with system context."""
		extraction = SheetExtraction(
			sheet_name=source.sheet_name,
			system=source.system,
			system_number=source.system_number,
		)

		try:
			payload = json.loads(_strip_fences(raw_text))
		except json.JSONDecodeError as exc:
			raise ProseExtractionError(
				f"Could not parse the model response as JSON for sheet "
				f"'{source.sheet_name}': {exc}"
			) from exc

		if not isinstance(payload, dict) or "devices" not in payload:
			raise ProseExtractionError(
				f"Model response for sheet '{source.sheet_name}' is missing "
				f"the 'devices' key."
			)

		raw_devices = payload.get("devices")
		if not isinstance(raw_devices, list):
			raise ProseExtractionError(
				f"'devices' is not a list in the response for sheet "
				f"'{source.sheet_name}'."
			)

		seen_ids: set[str] = set()
		for entry in raw_devices:
			if not isinstance(entry, dict):
				extraction.notes.append("Skipped a malformed device entry (not an object).")
				continue

			base_name = str(entry.get("base_name", "")).strip()
			if not base_name:
				extraction.notes.append("Skipped a device entry with no base_name.")
				continue

			device_class, class_ok = _coerce_class(entry.get("device_class", ""))
			confidence = _coerce_confidence(entry.get("confidence", ""))
			if not class_ok:
				# unknown class -> always force review, regardless of model claim
				confidence = Confidence.NEEDS_REVIEW
				extraction.notes.append(
					f"Device '{base_name}' had an unrecognized device_class "
					f"'{entry.get('device_class')}' — defaulted to Valve, flagged for review."
				)

			canonical = _canonical_id(source.system, source.system_number, base_name)
			# De-dup within a sheet — the model is told to merge, this is a backstop.
			if canonical in seen_ids:
				extraction.notes.append(
					f"Duplicate device '{base_name}' collapsed within sheet."
				)
				continue
			seen_ids.add(canonical)

			extraction.devices.append(
				DeviceRecord(
					canonical_id=canonical,
					device_class=device_class,
					system=source.system,
					system_number=source.system_number,
					base_name=base_name,
					description=str(entry.get("description", "")).strip(),
					source_reference=str(entry.get("source_reference", "")).strip()
					or source.sheet_name,
					source_type=SourceType.SEQUENCE_PROSE,
					confidence=confidence,
				)
			)

		return extraction

	# -- interface ------------------------------------------------------------
	def extract_sheet(self, source: ProseSource) -> SheetExtraction:
		if source.is_empty:
			# An empty sheet is a real, successful "no devices" result — not a
			# failure. The failure path is exceptions only (Plan §8.3).
			return SheetExtraction(
				sheet_name=source.sheet_name,
				system=source.system,
				system_number=source.system_number,
				notes=["Sheet had no prose content; nothing to extract."],
			)
		raw_text = self._call_api(source)
		return self._parse(raw_text, source)
