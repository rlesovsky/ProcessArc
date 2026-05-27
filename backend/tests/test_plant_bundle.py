"""Tests for the Plant Bundle Builder (backend/features/ignition_tags).

Covers donor.py, substitutor.py, plant_builder.py, and the new
plant_router endpoint POST /api/ignition-tags/build-plant.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.features.ignition_tags.donor import (
	RECOGNIZED_PLACEHOLDERS,
	load_donor,
)
from backend.features.ignition_tags.plant_builder import build_plant_bundle
from backend.features.ignition_tags.substitutor import (
	PARAMETER_BRACKETS,
	PlantIdentity,
	build_identity_from_request,
	build_renumber_map,
	substitute,
)


FIXTURES = Path(__file__).parent / "fixtures" / "ignition_tags"
XLSX_GOLDEN = FIXTURES / "golden_input.xlsx"

# Test plant identity reused across tests.
FAIRLESS = PlantIdentity(
	site_long="Fairless Hills PA 532",
	site_short="Fairless Hills",
	plant_num="532",
	region_code="PA",
	mqtt_topic="UFP Industries/532-Fairless Hills/PTS",
	main_project="_532_Fairless Hills",
)

PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")


def _walk_strings(node):
	if isinstance(node, dict):
		for v in node.values():
			yield from _walk_strings(v)
	elif isinstance(node, list):
		for v in node:
			yield from _walk_strings(v)
	elif isinstance(node, str):
		yield node


# ---------------------------------------------------------------------------
# donor.py
# ---------------------------------------------------------------------------


def test_load_donor_returns_tags_with_no_placeholder_errors():
	"""Every committed donor must load without errors."""
	for branch, count in [
		("cylinders", 2),
		("cylinders", 3),
		("mixing", 2),
		("mixing", 3),
		("plant_level", None),
	]:
		tags, issues = load_donor(branch, count)
		assert isinstance(tags, list) and len(tags) > 0, f"empty {branch} {count}"
		errors = [i for i in issues if i.severity == "error"]
		assert errors == [], f"{branch}/{count}: {errors}"


def test_load_donor_missing_file_raises_file_not_found():
	"""1-cylinder donor is deferred; loading it should raise."""
	try:
		load_donor("cylinders", 1)
	except FileNotFoundError:
		return
	raise AssertionError("Expected FileNotFoundError for missing 1-cylinder donor.")


def test_load_donor_unknown_placeholder_surfaces_error(tmp_path):
	"""A donor with an unrecognized __FOO__ token should fail loading."""
	# Patch DONORS_DIR via monkeypatching to point at a tmp dir with a
	# malformed donor.
	from backend.features.ignition_tags import donor as donor_module

	bad = {"branch": "plant_level", "count": None, "tags": [
		{"name": "X", "tagType": "AtomicTag", "value": "__NOT_A_REAL_PLACEHOLDER__"}
	]}
	(tmp_path / "plant_level.json").write_text(json.dumps(bad))
	original = donor_module.DONORS_DIR
	donor_module.DONORS_DIR = tmp_path
	try:
		# load_donor returns the tags + issues; the caller decides whether
		# to proceed. The error must surface so the caller can bail out.
		_tags, issues = load_donor("plant_level", None)
		codes = [i.code for i in issues if i.severity == "error"]
		assert "donor.placeholder_unsubstituted" in codes
	finally:
		donor_module.DONORS_DIR = original


def test_recognized_placeholders_match_substitutor():
	"""The donor loader and the substitutor must agree on the placeholder
	set, otherwise a placeholder that the substitutor doesn't know about
	would silently pass through."""
	from backend.features.ignition_tags import substitutor as sub_module
	identity = FAIRLESS.as_replacements()
	assert set(identity.keys()) == RECOGNIZED_PLACEHOLDERS


# ---------------------------------------------------------------------------
# substitutor.py
# ---------------------------------------------------------------------------


def test_placeholder_substitution_replaces_every_token():
	"""All recognized placeholders should be replaced; no leftovers."""
	donor = [{
		"name": "__SITE_LONG__",
		"tagType": "Folder",
		"tags": [
			{"name": "Topic", "tagType": "AtomicTag", "value": "__MQTT_TOPIC__"},
			{"name": "Proj", "tagType": "AtomicTag", "value": "__MAIN_PROJECT_NAME__"},
			{"name": "Short", "tagType": "AtomicTag", "value": "__SITE_SHORT__"},
		],
	}]
	out, _ = substitute(donor, identity=FAIRLESS)
	leftovers = set()
	for s in _walk_strings(out):
		leftovers.update(PLACEHOLDER_RE.findall(s))
	assert leftovers == set()
	# And the values landed correctly.
	tags = out[0]["tags"]
	assert tags[0]["value"] == "UFP Industries/532-Fairless Hills/PTS"
	assert tags[1]["value"] == "_532_Fairless Hills"
	assert tags[2]["value"] == "Fairless Hills"


def test_plc_parameter_brackets_pass_through_unchanged():
	"""{plc}, {PLC}, m{plc} are UDT parameter bindings; never rewritten."""
	donor = [{
		"name": "Edge", "tagType": "Folder",
		"tags": [
			{
				"name": "P1", "tagType": "AtomicTag",
				"opcItemPath": {"bindType": "parameter", "binding": "ns=1;s=[{plc}]MW100"},
			},
			{
				"name": "P2", "tagType": "AtomicTag",
				"opcItemPath": {"bindType": "parameter", "binding": "ns=1;s=[{PLC}]MW101"},
			},
			{
				"name": "P3", "tagType": "AtomicTag",
				"opcItemPath": {"bindType": "parameter", "binding": "ns=1;s=[m{plc}]MW102"},
			},
		],
	}]
	out, issues = substitute(donor, identity=FAIRLESS)
	# No bracket.rewritten warning emitted.
	codes = [i.code for i in issues]
	assert "bracket.rewritten" not in codes
	# Bindings are unchanged.
	assert out[0]["tags"][0]["opcItemPath"]["binding"] == "ns=1;s=[{plc}]MW100"
	assert out[0]["tags"][1]["opcItemPath"]["binding"] == "ns=1;s=[{PLC}]MW101"
	assert out[0]["tags"][2]["opcItemPath"]["binding"] == "ns=1;s=[m{plc}]MW102"


def test_leaked_bracket_in_opc_path_is_rewritten():
	"""A literal `[Hampton]` in a binding gets rewritten to the new short name."""
	donor = [{
		"name": "X", "tagType": "Folder",
		"tags": [{
			"name": "tag",
			"tagType": "AtomicTag",
			"opcItemPath": "ns=1;s=[Hampton]MW100",
		}],
	}]
	out, issues = substitute(donor, identity=FAIRLESS)
	codes = [i.code for i in issues]
	assert "bracket.rewritten" in codes
	assert out[0]["tags"][0]["opcItemPath"] == "ns=1;s=[Fairless Hills]MW100"


def test_bracket_rule_skips_non_opc_fields():
	"""Brackets in expression/script (which legitimately contain
	`[SCADA]`/`[System]`) are NOT defensively rewritten — the extraction
	script already cleaned `[SCADA]<long-name>/` leaks at extraction time."""
	donor = [{
		"name": "X", "tagType": "Folder",
		"tags": [{
			"name": "tag",
			"tagType": "AtomicTag",
			"expression": "tag('[SCADA]some/path') + tag('[System]Gateway/Database/X')",
		}],
	}]
	out, issues = substitute(donor, identity=FAIRLESS)
	codes = [i.code for i in issues]
	assert "bracket.rewritten" not in codes
	# expression untouched.
	assert "[SCADA]" in out[0]["tags"][0]["expression"]
	assert "[System]" in out[0]["tags"][0]["expression"]


def test_renumbering_renames_top_tags_and_path_strings():
	"""A cylinders donor with folders 1, 2 + mapping [1, 3] yields
	top folders 1, 3 AND any 'Cylinders/2/...' path strings become
	'Cylinders/3/...'."""
	donor = [
		{
			"name": "1", "tagType": "Folder",
			"tags": [{
				"name": "X", "tagType": "AtomicTag",
				"sourceTagPath": "[SCADA]__SITE_LONG__/Cylinders/1/Edge",
			}],
		},
		{
			"name": "2", "tagType": "Folder",
			"tags": [{
				"name": "X", "tagType": "AtomicTag",
				"sourceTagPath": "[SCADA]__SITE_LONG__/Cylinders/2/Edge",
			}],
		},
	]
	mapping = build_renumber_map([1, 3], 2)
	out, issues = substitute(donor, identity=FAIRLESS, branch="cylinders", cylinder_mapping=mapping)
	# Top folder renames.
	names = [t["name"] for t in out]
	assert names == ["1", "3"]
	# Path string in the second folder got renumbered too.
	assert out[1]["tags"][0]["sourceTagPath"] == (
		"[SCADA]Fairless Hills PA 532/Cylinders/3/Edge"
	)
	# Path string in the first folder is unchanged for Cylinders/1.
	assert out[0]["tags"][0]["sourceTagPath"] == (
		"[SCADA]Fairless Hills PA 532/Cylinders/1/Edge"
	)
	# A warning records the rename.
	codes = [i.code for i in issues]
	assert "cylinder.renumbered" in codes


def test_renumbering_identity_emits_no_warning():
	"""Default identity mapping (1→1, 2→2) is silent."""
	donor = [
		{"name": "1", "tagType": "Folder", "tags": []},
		{"name": "2", "tagType": "Folder", "tags": []},
	]
	mapping = build_renumber_map([1, 2], 2)
	_out, issues = substitute(donor, identity=FAIRLESS, branch="cylinders", cylinder_mapping=mapping)
	codes = [i.code for i in issues]
	assert "cylinder.renumbered" not in codes


def test_numeric_placeholder_coerced_to_int():
	"""Plant Info/Plant Number stored as the string '__PLANT_NUM__' in
	the donor should land as an int after substitution — Ignition's
	import expects integer-typed values where the source plant had one."""
	donor = [{
		"name": "Plant Info", "tagType": "Folder",
		"tags": [{
			"name": "Plant Number", "tagType": "AtomicTag",
			"value": "__PLANT_NUM__",
		}],
	}]
	out, _ = substitute(donor, identity=FAIRLESS)
	plant_num_tag = out[0]["tags"][0]
	assert plant_num_tag["value"] == 532
	assert isinstance(plant_num_tag["value"], int)


def test_build_identity_from_request_derives_mqtt_and_main_project():
	"""mqtt_topic and main_project default per UFP convention."""
	identity = build_identity_from_request({
		"site_long": "Test City PA 999",
		"site_short": "Test City",
		"plant_number": "999",
		"region_code": "PA",
	})
	assert identity.mqtt_topic == "UFP Industries/999-Test City/PTS"
	assert identity.main_project == "_999_Test City"


def test_build_identity_from_request_respects_overrides():
	"""When mqtt_topic/main_project are present in the config, they win."""
	identity = build_identity_from_request({
		"site_long": "Test City PA 999",
		"site_short": "Test City",
		"plant_number": "999",
		"region_code": "PA",
		"mqtt_topic": "CustomOrg/999-Test/PTS",
		"main_project": "_custom_999",
	})
	assert identity.mqtt_topic == "CustomOrg/999-Test/PTS"
	assert identity.main_project == "_custom_999"


def test_parameter_brackets_constant_is_complete():
	"""Make sure the {plc}/{PLC}/m{plc} set hasn't been silently shortened."""
	assert PARAMETER_BRACKETS == {"{plc}", "{PLC}", "m{plc}"}


# ---------------------------------------------------------------------------
# plant_builder.py
# ---------------------------------------------------------------------------


_FAIRLESS_CONFIG = {
	"site_long": "Fairless Hills PA 532",
	"site_short": "Fairless Hills",
	"plant_number": "532",
	"region_code": "PA",
	"cylinders": {"count": 2, "numbering": [1, 3]},
	"mixing": {"count": 2, "numbering": [1, 2]},
}


def test_build_plant_bundle_no_xlsx_produces_clean_tree():
	"""Build with default Fairless config and no xlsx — bundle is a single
	rooted folder named after the site, with the expected top children
	and zero leftover placeholders."""
	bundle, report, site, count = build_plant_bundle(_FAIRLESS_CONFIG, xlsx_bytes=None)
	assert site == "Fairless Hills PA 532"
	assert bundle["name"] == "Fairless Hills PA 532"
	assert bundle["tagType"] == "Folder"
	top_names = {c["name"] for c in bundle["tags"]}
	assert top_names == {"Cylinders", "Mixing", "Plant Info", "Treating Data", "Offline SQL", "Production"}
	assert count > 0
	# No leftover placeholders anywhere in the bundle.
	leftover = set()
	for s in _walk_strings(bundle):
		leftover.update(PLACEHOLDER_RE.findall(s))
	assert leftover == set()
	# Renumbering warning appears (cylinders 2 → 3).
	codes = [w.code for w in report.warnings]
	assert "cylinder.renumbered" in codes


def test_build_plant_bundle_cylinder_renumber_visible_in_tree():
	"""The Cylinders folder contains '1' and '3' (not '1' and '2')."""
	bundle, _report, _site, _count = build_plant_bundle(_FAIRLESS_CONFIG, xlsx_bytes=None)
	cyls = next(c for c in bundle["tags"] if c["name"] == "Cylinders")
	cyl_names = sorted(c["name"] for c in cyls["tags"])
	assert cyl_names == ["1", "3"]


def test_build_plant_bundle_missing_donor_returns_error():
	"""A 1-cylinder plant requests cylinders_1, which doesn't exist yet."""
	config = dict(_FAIRLESS_CONFIG)
	config["cylinders"] = {"count": 1, "numbering": [1]}
	bundle, report, _site, _count = build_plant_bundle(config, xlsx_bytes=None)
	assert bundle == {}
	codes = {e.code for e in report.errors}
	assert "donor.not_available" in codes


def test_build_plant_bundle_missing_required_field_returns_error():
	config = dict(_FAIRLESS_CONFIG)
	del config["site_long"]
	bundle, report, _site, _count = build_plant_bundle(config, xlsx_bytes=None)
	assert bundle == {}
	codes = {e.code for e in report.errors}
	assert "plant_config.missing_required" in codes


def test_build_plant_bundle_invalid_count_returns_error():
	config = dict(_FAIRLESS_CONFIG)
	config["cylinders"] = {"count": 5, "numbering": [1, 2, 3, 4, 5]}
	bundle, report, _site, _count = build_plant_bundle(config, xlsx_bytes=None)
	assert bundle == {}
	codes = {e.code for e in report.errors}
	assert "plant_config.invalid_count" in codes


def test_build_plant_bundle_numbering_length_mismatch_returns_error():
	config = dict(_FAIRLESS_CONFIG)
	config["cylinders"] = {"count": 2, "numbering": [1, 2, 3]}  # length 3 ≠ count 2
	bundle, report, _site, _count = build_plant_bundle(config, xlsx_bytes=None)
	assert bundle == {}
	codes = {e.code for e in report.errors}
	assert "plant_config.numbering_mismatch" in codes


def test_build_plant_bundle_with_xlsx_grafts_instances():
	"""Providing the xlsx grows the bundle by the xlsx's UdtInstance count
	(roughly — the xlsx may use sys_name/sys_num that overlap the donor
	tree, in which case overlapping leaves are replaced rather than
	added). With the synthetic fixture (which uses A1/01/...) the xlsx
	folders don't overlap the donor's Cylinders/* and Mixing/* paths, so
	all xlsx instances are added on top."""
	with XLSX_GOLDEN.open("rb") as f:
		xlsx_bytes = f.read()
	bundle_no_xlsx, _, _, count_no_xlsx = build_plant_bundle(_FAIRLESS_CONFIG, xlsx_bytes=None)
	bundle_xlsx, report, _, count_xlsx = build_plant_bundle(_FAIRLESS_CONFIG, xlsx_bytes=xlsx_bytes)
	assert count_xlsx > count_no_xlsx
	# Synthetic xlsx uses A1/01/LevelSensors etc. — paths don't exist in
	# donor; we should see the warning.
	codes = [w.code for w in report.warnings]
	assert "xlsx.path_not_in_donor" in codes


def test_renumber_map_handles_omitted_numbering():
	"""When numbering is not supplied, it defaults to identity."""
	from backend.features.ignition_tags.substitutor import build_renumber_map
	assert build_renumber_map(None, 3) == {1: 1, 2: 2, 3: 3}
	assert build_renumber_map([], 2) == {1: 1, 2: 2}


# ---------------------------------------------------------------------------
# plant_router.py — end-to-end
# ---------------------------------------------------------------------------


def test_e2e_build_plant_endpoint_returns_json_envelope():
	"""POST /api/ignition-tags/build-plant with no xlsx returns the same
	envelope shape as /build."""
	from fastapi.testclient import TestClient
	from backend.api.main import app

	client = TestClient(app)
	response = client.post(
		"/api/ignition-tags/build-plant",
		data={"plant_config": json.dumps(_FAIRLESS_CONFIG)},
	)
	assert response.status_code == 200, response.text
	body = response.json()
	assert set(body.keys()) >= {"bundle", "validation_report", "site", "instance_count"}
	assert body["site"] == "Fairless Hills PA 532"
	assert body["bundle"]["name"] == "Fairless Hills PA 532"
	assert body["bundle"]["tagType"] == "Folder"
	assert body["instance_count"] > 0


def test_e2e_build_plant_endpoint_accepts_optional_xlsx():
	"""xlsx_file is optional; when supplied, instance_count grows."""
	from fastapi.testclient import TestClient
	from backend.api.main import app

	client = TestClient(app)
	with XLSX_GOLDEN.open("rb") as f:
		response = client.post(
			"/api/ignition-tags/build-plant",
			data={"plant_config": json.dumps(_FAIRLESS_CONFIG)},
			files={"xlsx_file": ("golden_input.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
		)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["instance_count"] > 0


def test_e2e_build_plant_endpoint_returns_400_on_bad_config():
	from fastapi.testclient import TestClient
	from backend.api.main import app

	client = TestClient(app)
	response = client.post(
		"/api/ignition-tags/build-plant",
		data={"plant_config": json.dumps({"site_long": "X"})},  # incomplete
	)
	assert response.status_code == 400
	body = response.json()
	codes = {e["code"] for e in body["validation_report"]["errors"]}
	assert "plant_config.missing_required" in codes


def test_e2e_build_plant_endpoint_returns_400_on_invalid_json():
	from fastapi.testclient import TestClient
	from backend.api.main import app

	client = TestClient(app)
	response = client.post(
		"/api/ignition-tags/build-plant",
		data={"plant_config": "{not-valid-json"},
	)
	assert response.status_code == 400


def test_existing_build_endpoint_unchanged():
	"""Regression: /build still works exactly as before — this feature
	must not touch it."""
	from fastapi.testclient import TestClient
	from backend.api.main import app

	client = TestClient(app)
	with XLSX_GOLDEN.open("rb") as f:
		response = client.post(
			"/api/ignition-tags/build",
			files={"file": ("golden_input.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
		)
	assert response.status_code == 200, response.text
	body = response.json()
	assert body["site"] == "UFP_Athens"
	assert body["bundle"]["name"] == "UFP_Athens"
