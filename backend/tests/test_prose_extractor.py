"""Offline tests for the Prose Extractor (Plan §8).

Uses a fake `anthropic`-shaped client passed through `ClaudeProseExtractor`'s
injection seam — no network, no API key, no real UFP prose. These are the
contract guarantees that downstream code relies on; if any of them break, the
Extract screen and the Review screen would start lying to the engineer.
"""

from __future__ import annotations

import json

import pytest

from backend.extract.prose import (
	ClaudeProseExtractor,
	ProseExtractionError,
	ProseExtractor,
	ProseSource,
	SheetExtraction,
)
from backend.model.device import (
	Confidence,
	DeviceClass,
	SourceType,
	SystemKind,
)


# =============================================================================
# Fake `anthropic` client — just enough surface for the extractor to use
# =============================================================================
class _FakeBlock:
	def __init__(self, text: str) -> None:
		self.text = text
		self.type = "text"


class _FakeResponse:
	def __init__(self, content_blocks) -> None:
		self.content = content_blocks


class _FakeMessages:
	def __init__(self, behavior) -> None:
		self._behavior = behavior  # callable(kwargs) -> str | Exception
		self.calls: list[dict] = []

	def create(self, **kwargs):
		self.calls.append(kwargs)
		out = self._behavior(kwargs)
		if isinstance(out, Exception):
			raise out
		return _FakeResponse([_FakeBlock(out)])


class _FakeClient:
	def __init__(self, behavior) -> None:
		self.messages = _FakeMessages(behavior)


def _ok(devices: list[dict]) -> str:
	return json.dumps({"devices": devices})


def _source(**overrides) -> ProseSource:
	defaults = dict(
		sheet_name="Cylinder 3 Sequencing",
		system=SystemKind.CYLINDERS,
		system_number=3,
		lines=["Step 1 — open VPD valve.", "Step 2 — start P1 pump."],
	)
	defaults.update(overrides)
	return ProseSource(**defaults)


# =============================================================================
# 1. Interface conformance
# =============================================================================
def test_prose_extractor_is_abstract():
	with pytest.raises(TypeError):
		ProseExtractor()  # type: ignore[abstract]


def test_claude_extractor_implements_interface():
	e = ClaudeProseExtractor(client=_FakeClient(lambda _: _ok([])))
	assert isinstance(e, ProseExtractor)


# =============================================================================
# 2. System-context stamping (Plan §8.2)
# =============================================================================
def test_devices_inherit_cylinder_system_from_caller():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "VPD", "device_class": "Valve", "description": "x",
		 "confidence": "High", "source_reference": "step 1"},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(_source()).devices[0]
	assert d.system == SystemKind.CYLINDERS
	assert d.system_number == 3
	assert d.canonical_id == "CYL3_VPD"


def test_devices_inherit_mix_system_from_caller():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "MP1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(
		_source(system=SystemKind.MIXING, system_number=2)
	).devices[0]
	assert d.system == SystemKind.MIXING
	assert d.system_number == 2
	assert d.canonical_id == "MIX2_MP1"


def test_unnumbered_system_yields_x_canonical():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "V1", "device_class": "Valve", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(
		_source(system_number=None)
	).devices[0]
	assert d.system_number is None
	assert d.canonical_id == "CYLX_V1"


def test_source_type_is_sequence_prose():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(_source()).devices[0]
	assert d.source_type == SourceType.SEQUENCE_PROSE


# =============================================================================
# 3. Failure contract (Plan §8.3) — every failure raises; never empty list
# =============================================================================
def test_api_exception_is_wrapped():
	client = _FakeClient(lambda _: RuntimeError("network down"))
	with pytest.raises(ProseExtractionError, match="network down"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


# ---- Typed anthropic errors → actionable messages ---------------------------
# The extractor catches anthropic's typed error hierarchy and re-raises with
# messages the Extract screen can act on. These tests use the real anthropic
# classes (instantiated minimally) so the isinstance dispatch is exercised
# without making a network call.
def _make_anthropic_error(error_cls):
	"""Construct a real anthropic error instance for isinstance dispatch."""
	import anthropic
	import httpx
	# Most anthropic error classes accept (message, *, response, body). A
	# minimal fake response is enough — we only care about the exception type.
	request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
	if error_cls is anthropic.APIConnectionError:
		return error_cls(request=request)
	if error_cls is anthropic.APITimeoutError:
		return error_cls(request=request)
	# Status-error subclasses take a response object.
	response = httpx.Response(429 if error_cls is anthropic.RateLimitError else 400,
	                          request=request)
	return error_cls(message="x", response=response, body=None)


def test_authentication_error_gives_actionable_message():
	import anthropic
	exc = _make_anthropic_error(anthropic.AuthenticationError)
	client = _FakeClient(lambda _: exc)
	with pytest.raises(ProseExtractionError, match="valid key|Settings"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_rate_limit_error_gives_actionable_message():
	import anthropic
	exc = _make_anthropic_error(anthropic.RateLimitError)
	client = _FakeClient(lambda _: exc)
	with pytest.raises(ProseExtractionError, match="rate limited"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_api_timeout_error_gives_actionable_message():
	import anthropic
	exc = _make_anthropic_error(anthropic.APITimeoutError)
	client = _FakeClient(lambda _: exc)
	with pytest.raises(ProseExtractionError, match="timed out"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_api_connection_error_gives_actionable_message():
	import anthropic
	exc = _make_anthropic_error(anthropic.APIConnectionError)
	client = _FakeClient(lambda _: exc)
	with pytest.raises(ProseExtractionError, match="Could not reach|network"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_bad_request_error_flags_likely_model_name_issue():
	import anthropic
	exc = _make_anthropic_error(anthropic.BadRequestError)
	client = _FakeClient(lambda _: exc)
	with pytest.raises(ProseExtractionError, match="invalid model name"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


# ---- timeout= is passed through to the SDK ----------------------------------
def test_timeout_passed_to_messages_create():
	captured: dict = {}

	def behavior(kwargs):
		captured.update(kwargs)
		return _ok([])

	ClaudeProseExtractor(client=_FakeClient(behavior), timeout_s=42.5).extract_sheet(_source())
	assert captured["timeout"] == 42.5


def test_default_timeout_is_set():
	captured: dict = {}

	def behavior(kwargs):
		captured.update(kwargs)
		return _ok([])

	ClaudeProseExtractor(client=_FakeClient(behavior)).extract_sheet(_source())
	assert "timeout" in captured
	assert captured["timeout"] > 0


def test_empty_response_blocks_raises():
	class _Empty:
		class messages:
			@staticmethod
			def create(**kwargs):
				return _FakeResponse([])
	with pytest.raises(ProseExtractionError, match="no text content"):
		ClaudeProseExtractor(client=_Empty()).extract_sheet(_source())


def test_non_json_response_raises():
	client = _FakeClient(lambda _: "this is not json")
	with pytest.raises(ProseExtractionError, match="parse"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_missing_devices_key_raises():
	client = _FakeClient(lambda _: json.dumps({"items": []}))
	with pytest.raises(ProseExtractionError, match="missing the 'devices' key"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_devices_not_a_list_raises():
	client = _FakeClient(lambda _: json.dumps({"devices": "huh"}))
	with pytest.raises(ProseExtractionError, match="not a list"):
		ClaudeProseExtractor(client=client).extract_sheet(_source())


def test_failure_never_returns_silently():
	"""A failure must NEVER look like a successful zero-device run."""
	client = _FakeClient(lambda _: RuntimeError("boom"))
	try:
		ClaudeProseExtractor(client=client).extract_sheet(_source())
	except ProseExtractionError:
		return
	pytest.fail("extractor returned without raising on a failure")


def test_extract_all_stops_on_first_failure():
	attempts = []

	def behavior(kwargs):
		attempts.append(kwargs)
		return RuntimeError("nope")

	with pytest.raises(ProseExtractionError):
		ClaudeProseExtractor(client=_FakeClient(behavior)).extract_all(
			[_source(sheet_name="A"), _source(sheet_name="B")]
		)
	assert len(attempts) == 1, "should have stopped after the first failure"


# =============================================================================
# 4. Empty-sheet handling — empty = success, not failure
# =============================================================================
def test_empty_sheet_is_successful_zero_device():
	result = ClaudeProseExtractor(client=_FakeClient(lambda _: _ok([]))).extract_sheet(
		_source(lines=[])
	)
	assert isinstance(result, SheetExtraction)
	assert result.devices == []
	assert any("no prose content" in n.lower() for n in result.notes)


def test_empty_sheet_does_not_call_api():
	called: list = []
	client = _FakeClient(lambda kw: called.append(kw) or _ok([]))
	ClaudeProseExtractor(client=client).extract_sheet(_source(lines=["", "  ", "\t"]))
	assert called == []


def test_whitespace_only_lines_are_empty():
	assert _source(lines=["", " ", "\t"]).is_empty


# =============================================================================
# 5. Defensive parsing
# =============================================================================
def test_strips_json_fences():
	payload = "```json\n" + _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]) + "\n```"
	d = ClaudeProseExtractor(client=_FakeClient(lambda _: payload)).extract_sheet(
		_source()
	).devices[0]
	assert d.base_name == "P1"


def test_strips_bare_fences_without_lang():
	payload = "```\n" + _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]) + "\n```"
	d = ClaudeProseExtractor(client=_FakeClient(lambda _: payload)).extract_sheet(
		_source()
	).devices[0]
	assert d.base_name == "P1"


def test_unknown_device_class_forced_to_review():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "X9", "device_class": "Unicorn", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	result = ClaudeProseExtractor(client=client).extract_sheet(_source())
	d = result.devices[0]
	assert d.confidence == Confidence.NEEDS_REVIEW
	assert d.device_class == DeviceClass.VALVE  # safe default
	assert any("unrecognized device_class" in n for n in result.notes)


def test_class_match_is_case_insensitive():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "P1", "device_class": "vfd pump", "description": "",
		 "confidence": "high", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(_source()).devices[0]
	assert d.device_class == DeviceClass.VFD_PUMP
	assert d.confidence == Confidence.HIGH


def test_duplicate_within_sheet_collapsed():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "VPD", "device_class": "Valve", "description": "",
		 "confidence": "High", "source_reference": "step 1"},
		{"base_name": "VPD", "device_class": "Valve", "description": "",
		 "confidence": "High", "source_reference": "step 2"},
	]))
	result = ClaudeProseExtractor(client=client).extract_sheet(_source())
	assert len(result.devices) == 1
	assert any("duplicate" in n.lower() for n in result.notes)


def test_missing_base_name_skipped():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "", "device_class": "Valve", "description": "",
		 "confidence": "High", "source_reference": ""},
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	result = ClaudeProseExtractor(client=client).extract_sheet(_source())
	assert [d.base_name for d in result.devices] == ["P1"]
	assert any("no base_name" in n for n in result.notes)


def test_malformed_entry_skipped():
	payload = json.dumps({"devices": [
		"not-an-object",
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]})
	result = ClaudeProseExtractor(client=_FakeClient(lambda _: payload)).extract_sheet(_source())
	assert [d.base_name for d in result.devices] == ["P1"]
	assert any("malformed" in n.lower() for n in result.notes)


def test_unknown_confidence_defaults_to_review():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "Maybe", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(_source()).devices[0]
	assert d.confidence == Confidence.NEEDS_REVIEW


def test_canonical_id_strips_non_alnum():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "V-9.A", "device_class": "Valve", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(_source()).devices[0]
	assert d.canonical_id == "CYL3_V9A"


def test_source_reference_falls_back_to_sheet_name():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	d = ClaudeProseExtractor(client=client).extract_sheet(
		_source(sheet_name="Cylinder 1 Sequencing")
	).devices[0]
	assert d.source_reference == "Cylinder 1 Sequencing"


# =============================================================================
# 6. Prompt construction
# =============================================================================
def _capture():
	captured: dict = {}

	def behavior(kwargs):
		captured.update(kwargs)
		return _ok([])

	return captured, behavior


def test_user_prompt_includes_system_context():
	captured, behavior = _capture()
	ClaudeProseExtractor(client=_FakeClient(behavior)).extract_sheet(
		_source(system=SystemKind.CYLINDERS, system_number=3,
		        sheet_name="Cylinder 3 Sequencing", lines=["Step 1 — open VPD."])
	)
	msg = captured["messages"][0]["content"]
	assert "System: Cylinders" in msg
	assert "System Number: 3" in msg
	assert "Cylinder 3 Sequencing" in msg
	assert "Step 1 — open VPD." in msg


def test_unnumbered_system_renders_explicitly():
	captured, behavior = _capture()
	ClaudeProseExtractor(client=_FakeClient(behavior)).extract_sheet(
		_source(system_number=None)
	)
	assert "System Number: (unnumbered)" in captured["messages"][0]["content"]


def test_system_prompt_contains_every_device_class():
	captured, behavior = _capture()
	ClaudeProseExtractor(client=_FakeClient(behavior)).extract_sheet(_source())
	for cls in ("Pump", "VFD Pump", "Valve", "Control Valve", "Tank"):
		assert cls in captured["system"]


def test_uses_configured_model_override():
	captured, behavior = _capture()
	ClaudeProseExtractor(model="custom-model", client=_FakeClient(behavior)).extract_sheet(
		_source()
	)
	assert captured["model"] == "custom-model"


# =============================================================================
# 7. extract_all aggregation
# =============================================================================
def test_extract_all_aggregates_across_sheets():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	result = ClaudeProseExtractor(client=client).extract_all([
		_source(sheet_name="A", system_number=1),
		_source(sheet_name="B", system_number=2),
	])
	assert result.device_count == 2
	assert {d.system_number for d in result.devices} == {1, 2}


def test_needs_review_filter():
	client = _FakeClient(lambda _: _ok([
		{"base_name": "P1", "device_class": "Pump", "description": "",
		 "confidence": "Needs Review", "source_reference": ""},
		{"base_name": "P2", "device_class": "Pump", "description": "",
		 "confidence": "High", "source_reference": ""},
	]))
	result = ClaudeProseExtractor(client=client).extract_all([_source()])
	nr = result.needs_review()
	assert [d.base_name for d in nr] == ["P1"]
