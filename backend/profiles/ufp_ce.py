"""UFP Cause Library + C&E Profile (Plan §7.4, §10).

The cause library describes the *patterns* — not the actual rows of a finished
C&E. Actual rows are generated from the patterns scaled to the Plant
Configuration at export time: one set of cylinder interlock rows per active
cylinder, one tank-volume row per tank, etc.

Per Plan §0 the Phase 1 build is UFP-specific, so the profile is hardcoded
here. The data shape is deliberately simple so future versions can load it
from disk (Plan §13 Q4 — ownership/versioning of the profile).

Cells in the matrix carry the legend codes from the Fairless Hills C&E:
  P  Pause            C  Close valve    O  Open valve
  E  Energize         D  De-energize    A  Alarm
  SA System Active

A cell value of `""` is the engineer's blank — judgment required (Plan §10.2
Step D). Generated rows include a `note` field that says when judgment is
needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from backend.model import DeviceClass, DeviceRecord, ReviewStatus, SystemKind
from backend.model.plant import PlantConfiguration


# =============================================================================
# Action codes
# =============================================================================
class Code:
	PAUSE = "P"
	CLOSE = "C"
	OPEN = "O"
	ENERGIZE = "E"
	DE_ENERGIZE = "D"
	ALARM = "A"
	SYSTEM_ACTIVE = "SA"


# =============================================================================
# A cause row
# =============================================================================
@dataclass
class CauseRow:
	"""One row of the C&E matrix.

	`note`, `cause`, `alarm`, `setpoint` are the four leading text columns of
	the UFP C&E. `effects` is a sparse mapping from column-key → action code.
	Keys are either a sequence-control column id (`"Treat:1"`, `"Mix:2"`) or a
	device canonical_id. Unset cells are left blank.
	"""

	note: str
	cause: str
	alarm: str  # "Y" / "N" / ""
	setpoint: str
	effects: dict[str, str] = field(default_factory=dict)


# =============================================================================
# The profile — describes how to build a C&E for a given plant + device list
# =============================================================================
@dataclass
class CEProfile:
	"""How to assemble the C&E matrix.

	`generators` is a list of callables; each takes (plant, devices) and
	returns a list of CauseRows. The exporter concatenates them in order. New
	cause patterns are added by appending a new generator.
	"""

	name: str
	generators: list[Callable[[PlantConfiguration, list[DeviceRecord]], list[CauseRow]]]


# =============================================================================
# Helpers — column ids the exporter recognizes
# =============================================================================
def treat_col(num: int) -> str:
	return f"Treat:{num}"


def mix_col(num: int) -> str:
	return f"Mix:{num}"


def _active_cylinder_numbers(plant: PlantConfiguration) -> list[int]:
	return [c.number for c in plant.cylinders if not c.is_idle]


def _mix_numbers(plant: PlantConfiguration) -> list[int]:
	return [m.number for m in plant.mix_systems]


def _eligible_devices(devices: list[DeviceRecord]) -> list[DeviceRecord]:
	return [d for d in devices if d.review_status != ReviewStatus.EXCLUDED]


def _devices_for_system(
	devices: list[DeviceRecord], system: SystemKind, number: int
) -> list[DeviceRecord]:
	return [
		d for d in _eligible_devices(devices)
		if d.system == system and d.system_number == number
	]


# =============================================================================
# Cause generators — patterns from the UFP C&E read file
# =============================================================================
def _estop_row(plant: PlantConfiguration, devices: list[DeviceRecord]) -> list[CauseRow]:
	"""Emergency Stop — Pause every sequence-control column; close every
	non-excluded valve; de-energize every pump. (UFP C&E legend §4.3 row 1.)
	"""
	effects: dict[str, str] = {}
	for n in _active_cylinder_numbers(plant):
		effects[treat_col(n)] = Code.PAUSE
	for n in _mix_numbers(plant):
		effects[mix_col(n)] = Code.PAUSE
	for d in _eligible_devices(devices):
		if d.device_class in (DeviceClass.VALVE, DeviceClass.CONTROL_VALVE):
			effects[d.canonical_id] = Code.CLOSE
		elif d.device_class in (DeviceClass.PUMP, DeviceClass.VFD_PUMP):
			effects[d.canonical_id] = Code.DE_ENERGIZE
	return [CauseRow(note="", cause="Estop", alarm="Y", setpoint="", effects=effects)]


def _system_pause_rows(plant: PlantConfiguration, devices: list[DeviceRecord]) -> list[CauseRow]:
	"""One System-Pause row per active cylinder and per mix system."""
	rows: list[CauseRow] = []
	for n in _active_cylinder_numbers(plant):
		sys_devices = _devices_for_system(devices, SystemKind.CYLINDERS, n)
		effects = {treat_col(n): Code.PAUSE}
		for d in sys_devices:
			if d.device_class in (DeviceClass.VALVE, DeviceClass.CONTROL_VALVE):
				effects[d.canonical_id] = Code.CLOSE
		rows.append(CauseRow(
			note="From SCADA screen",
			cause=f"Treat{n} System Pause",
			alarm="N", setpoint="",
			effects=effects,
		))
	for n in _mix_numbers(plant):
		sys_devices = _devices_for_system(devices, SystemKind.MIXING, n)
		effects = {mix_col(n): Code.PAUSE}
		for d in sys_devices:
			if d.device_class in (DeviceClass.VALVE, DeviceClass.CONTROL_VALVE):
				effects[d.canonical_id] = Code.CLOSE
		rows.append(CauseRow(
			note="From SCADA screen",
			cause=f"Mix{n} System Pause",
			alarm="N", setpoint="",
			effects=effects,
		))
	return rows


def _field_estop_rows(plant: PlantConfiguration, devices: list[DeviceRecord]) -> list[CauseRow]:
	"""The four field e-stops — each pauses every Treat/Mix column."""
	rows: list[CauseRow] = []
	all_seq_effects: dict[str, str] = {}
	for n in _active_cylinder_numbers(plant):
		all_seq_effects[treat_col(n)] = Code.PAUSE
	for n in _mix_numbers(plant):
		all_seq_effects[mix_col(n)] = Code.PAUSE
	for d in _eligible_devices(devices):
		if d.device_class in (DeviceClass.VALVE, DeviceClass.CONTROL_VALVE):
			all_seq_effects[d.canonical_id] = Code.CLOSE

	for i in (1, 2, 3, 4):
		rows.append(CauseRow(
			note="",
			cause=f"FldEmergencyStop{i}_IN",
			alarm="Y",
			setpoint="0=alarm, 1=good",
			effects=dict(all_seq_effects),
		))
	rows.append(CauseRow(
		note="",
		cause="PowerFail_In",
		alarm="Y",
		setpoint="0=alarm, 1=good",
		effects=dict(all_seq_effects),
	))
	return rows


def _overpsi_rows(plant: PlantConfiguration, devices: list[DeviceRecord]) -> list[CauseRow]:
	"""Treat{N}OverPSI — pauses only that cylinder. One row per active cylinder."""
	rows: list[CauseRow] = []
	for n in _active_cylinder_numbers(plant):
		rows.append(CauseRow(
			note="",
			cause=f"Treat{n}OverPSI",
			alarm="Y",
			setpoint="0=alarm if treating",
			effects={treat_col(n): Code.PAUSE},
		))
	return rows


def _door_interlock_rows(plant: PlantConfiguration, devices: list[DeviceRecord]) -> list[CauseRow]:
	"""Per active cylinder, the standard door interlock pattern (UFP C&E §4.3)."""
	rows: list[CauseRow] = []
	for n in _active_cylinder_numbers(plant):
		for door in (1, 2):
			for part in ("Lever", "Ring", "Swing"):
				rows.append(CauseRow(
					note="",
					cause=f"Treat{n}Door{door}{part}Closed",
					alarm="Y",
					setpoint="0=alarm if treating",
					effects={treat_col(n): Code.PAUSE},
				))
	return rows


def _tank_volume_rows(plant: PlantConfiguration, devices: list[DeviceRecord]) -> list[CauseRow]:
	"""One row per tank. Tanks tied to a cylinder via Cylinder Used drive a
	low/HiHi pause on that cylinder; supply tanks alarm only.

	Cells where the engineer must decide are left blank with a clear note —
	per Plan §10.2 Step D ("leave judgment cells blank but marked").
	"""
	rows: list[CauseRow] = []
	for t in plant.tanks:
		effects: dict[str, str] = {}
		notes = []
		if t.cylinder_used is not None and t.cylinder_used in _active_cylinder_numbers(plant):
			effects[treat_col(t.cylinder_used)] = "P[L],[HH]"
			notes.append(f"only if Tank {t.tank_id} is selected for Treat{t.cylinder_used}")
		else:
			notes.append("alarm only — supply tank, no cylinder pause")
		rows.append(CauseRow(
			note="; ".join(notes),
			cause=f"Tank[{t.tank_id}].Volume",
			alarm="Y",
			setpoint="Modular, SCADA-based",
			effects=effects,
		))
	return rows


# =============================================================================
# Public profile
# =============================================================================
class UFPCauseLibrary:
	"""Container for the generator catalog so it's easy to inspect/extend."""

	@staticmethod
	def all() -> list[Callable]:
		return [
			_estop_row,
			_system_pause_rows,
			_field_estop_rows,
			_overpsi_rows,
			_door_interlock_rows,
			_tank_volume_rows,
		]


def get_ufp_ce_profile() -> CEProfile:
	return CEProfile(name="UFP Phase 1", generators=UFPCauseLibrary.all())
