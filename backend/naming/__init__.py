"""Naming Rule Engine (Plan §6.2).

Renders canonical device records into the names each output uses, using each
device's own System Number and Base Name — never an assumed value.

Two outputs care about names:
  - Ignition IO list: name = base_name (already the canonical short name).
  - C&E output tag: pattern depends on device class —
      Valve         : Treat{N}_{BaseName}vlv_Out      (Mixing: Mix{N}_…)
      Control Valve : Treat{N}_{BaseName}cv_Out
      Pump          : Treat{N}_{BaseName}pmp_Out
      VFD Pump      : Treat{N}_{BaseName}_VFD_Out
      Tank          : Treat{N}_{BaseName}tnk

Plan §13 Q1 calls out that the full UFP catalog of output-tag patterns needs
to be confirmed. Phase 1 implements the patterns visible in the existing UFP
docs and flags unknown classes — better to leave a clear pointer in the
output than to silently guess.
"""

from __future__ import annotations

from typing import Optional

from backend.model.device import DeviceClass, DeviceRecord, SystemKind


def ignition_name(device: DeviceRecord) -> str:
	"""The name that appears in the IO list. Plan §4 keeps this verbatim from
	the sequence — the engineer's edits in Review already reshaped it if
	needed. The IO list writes the device's base_name as-is.
	"""
	return device.base_name


def ce_output_tag(device: DeviceRecord) -> str:
	"""The Cause & Effect output tag (Plan §6.2 + §13 Q1).

	Returns the rendered C&E tag, or a flagged string of the form
	"<<UNKNOWN_CLASS:{class}>>" so the engineer can spot un-mapped patterns
	in the exported sheet rather than getting a quiet wrong name.
	"""
	prefix = _system_prefix(device.system, device.system_number)
	suffix = _ce_suffix_for_class(device.device_class)
	if suffix is None:
		return f"<<UNKNOWN_CLASS:{device.device_class.value}>>"
	return f"{prefix}_{device.base_name}{suffix}"


def _system_prefix(system: SystemKind, number: Optional[int]) -> str:
	n = number if number is not None else "X"
	if system == SystemKind.CYLINDERS:
		return f"Treat{n}"
	return f"Mix{n}"


# Per-class C&E suffix. Q1 flags this catalog as needing confirmation;
# `None` means "we don't have a confirmed pattern for this class — flag it."
_CE_SUFFIX: dict[DeviceClass, str] = {
	DeviceClass.VALVE: "vlv_Out",
	DeviceClass.CONTROL_VALVE: "cv_Out",
	DeviceClass.PUMP: "pmp_Out",
	DeviceClass.VFD_PUMP: "_VFD_Out",
	DeviceClass.TANK: "tnk",
}


def _ce_suffix_for_class(cls: DeviceClass) -> Optional[str]:
	return _CE_SUFFIX.get(cls)
