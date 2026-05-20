"""UFP standard register pattern data (Plan §9A).

This is the *inferred* pattern from the Fairless Hills Ignition file's Tank
sheet. Plan §13 Q11 calls out that the PLC team must confirm which blocks
UFP keeps constant across plants. Until that confirmation lands per-class,
the safe default is: pre-fill what we see at Fairless Hills, and let the
engineer correct it in Excel after export.

Pattern shape: each field maps to (prefix, base_address, block_size, offset).
The address for tank instance N (1-indexed) is computed as:

    f"{prefix}{base + block_size * (N - 1) + offset}"

Two blocks per tank, both observed in the Fairless Hills Ignition Tank sheet:
  - TankIn  : 14-word block per instance, starting MW1872
  - TankOut :  8-word block per instance, starting MW2744
"""

from __future__ import annotations

from typing import Optional


# (prefix, base, block_size, offset_within_block)
RegisterPatternEntry = tuple[str, int, int, int]


TANK_REGISTER_PATTERN: dict[str, RegisterPatternEntry] = {
	# TankIn block — 14-word stride, base MW1872 (Diameter base).
	"TankIn.Diameter":         ("MW", 1872, 14, 0),
	"TankIn.Density":          ("MW", 1872, 14, 2),
	"TankIn.TankType":         ("MW", 1872, 14, 4),
	"TankIn.Length":           ("MW", 1872, 14, 6),
	"TankIn.Minimum":          ("MW", 1872, 14, 8),
	"TankIn.Pump":             ("MW", 1872, 14, 12),
	# TankOut block — 8-word stride, base MW2744 (Volume base).
	"TankOut.Volume":          ("MW", 2744, 8, 0),
	"TankOut.Temp":            ("MW", 2744, 8, 2),
	"TankOut.Bits":            ("MW", 2744, 8, 4),
	"TankOut.Current Status":  ("MW", 2744, 8, 6),
}


def tank_register_for(field: str, slot: int) -> Optional[str]:
	"""Compute the MW address for `field` at the 1-based tank `slot`.

	Returns None if there is no standard pattern for the field — the caller
	should leave that column blank for the PLC programmers.
	"""
	pattern = TANK_REGISTER_PATTERN.get(field)
	if pattern is None:
		return None
	prefix, base, block_size, offset = pattern
	address = base + block_size * (slot - 1) + offset
	return f"{prefix}{address}"
