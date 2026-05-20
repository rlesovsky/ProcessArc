"""Sequence-line classifier for the Treating Sequence document exporter.

Each raw prose line from a cylinder or mix sequencing sheet is sorted into one
`LineType`. The document builder (`sequence_doc.py`) renders each type
distinctively — numbered actions, separated transition conditions, nested
conditionals, callout notes.

This is deterministic, offline, and free — no Claude API call. It is a
presentation aid for the customer's prose, not device extraction (that is the
Prose Extractor's job, `backend/extract/prose.py`). Ambiguous lines fall back
to PROSE and are always still rendered — never dropped.

Typo handling: a small, closed set of unambiguous spelling corrections is
applied to the display text. Every correction is recorded on the line so the
document can mark it and list it in an Editorial Notes section. Device names,
numbers, and operational wording are never altered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LineType(str, Enum):
	SECTION_TITLE = "section_title"        # "Cylinder 1 Step by Step Sequence" — redundant
	STEP_HEADER = "step_header"            # "Initial Vacuum:" — a named phase, gets a number
	GROUP_HEADER = "group_header"          # "For mixing Tanks 3 and 5:" — mix sub-group label
	TRANSITION = "transition"              # "Step advance on ..." — the rule that ends a step
	ACTION = "action"                      # "Open V1, V5, V6" — an operational step
	CONDITIONAL = "conditional"            # "If treating Tank 1, open S3" — a gated action
	NOTE = "note"                          # "confirm in PLC?", customer requests/questions
	PROSE = "prose"                        # anything unclassified — shown verbatim as-is


# Known cylinder step-header names seen across UFP plants. A strong signal;
# the structural rule below still catches unfamiliar step names on other sites.
_KNOWN_STEPS = {
	"initial vacuum", "fill", "raise pressure", "pressure", "pressure relief",
	"empty", "final vacuum", "final empty", "finish",
}

_TRANSITION_RE = re.compile(
	# "Step advance ..." / "Step completes ..." — original Fairless wording.
	# "System step on ..." / "System advance(s) on ..." — Hampton wording.
	# "System should step ..." — Hampton uncertainty variant.
	# "The step advances on ..." — alternate Hampton phrasing.
	r"^\s*("
	r"step\s+(advance|completes|complete)|"
	r"system\s+(step|advance|advances|should\s+step)\b|"
	r"the\s+step\s+advance(s|d)?\b|"
	r".*\bstep\s+advance\b|"
	r"max\s+time\s+in\s+cycle"
	r")",
	re.IGNORECASE,
)

# Operational verbs / subjects that begin an action line.
#
# Hampton-specific additions (vs. Fairless Hills):
#   - Delay-clause prefix: "on 1 second delay, turn off ..."
#   - Bare delay: "1 second delay then close ..."
#   - Bare `turn` (Hampton writes "Turn pressure pump on N second delay ...").
#   - Infinitive purpose clause: "To run the strip pump, open ..."
#   - Verbs: "raise", "lower"
#   - Device-name + state verb. The subject can be one short name
#     ("VPD remain") or a comma/parenthesized list ("Tank valve, P1, P2 remain";
#     "Tank Valve (V2-1 or V3-1) remains"; "Water tank fill valve VCW turns on").
#   - Pump types Hampton uses verbatim: "seal water pump", "vac pump", and the
#     bare device names "vpd", "vps", "vss".
_ACTION_VERB_RE = re.compile(
	r"^\s*("
	# Position-0 operational verbs. Bare `turn` covers "Turn X on/off/back on".
	r"open|close|turn\b|start|stop|run|after|once|"
	r"select|continue|raise|lower|"
	# Delay-clause prefixes.
	r"on\s+\d+\s+second\s+delay\b|"
	r"\d+\s+second\s+delay\s+then\b|"
	# Infinitive purpose clause: "To run the strip pump, open S1 ...",
	# "To mix tank 1, start by opening MD1".
	r"to\s+(run|start|open|close|turn|empty|fill|raise|lower|drain|mix)\s+"
	r")",
	re.IGNORECASE,
)


# State-verb pattern, applied independently of _ACTION_VERB_RE. Catches
# device-subject lines like "Tank valve, P1, P2 remain open" or "Water tank
# fill valve VCW turns on" — the subject may be 1-6 words, possibly with
# commas, slashes, or parenthesized device names.
_STATE_VERB_RE = re.compile(
	# Subject: word chars / digits / device punctuation, 1-7 such tokens.
	r"^\s*[\w\-/]+(?:[\s,()/-]+[\w\-/]+){0,6}\s+"
	# State verbs.
	r"(remain|remains|continue|continues|carry|carries|"
	r"close|closes|open|opens|shut|shuts|"
	r"turns?\s+(on|off)|"
	r"is\s+(open|closed|used|on|off)|are\s+(open|closed|used|on|off)|"
	r"stays?\s+(open|closed|on|off)|"
	r"runs?\s+(at|until)"
	r")\b",
	re.IGNORECASE,
)

# Device names Hampton uses as bare sentence subjects (matched after the main
# verb / state-verb patterns fail, so they don't preempt structured matches).
_DEVICE_SUBJECT_RE = re.compile(
	r"^\s*(vpd|vps|vss|vsd|vwv|cwv|t\d+|s\d+|p\d+|v\d+|c\d+|"
	r"tankv\d+|tnkv\d+|md\d+|ms\d+|vmt\d+|vmd\d+|vms\d+)\b",
	re.IGNORECASE,
)

_CONDITIONAL_RE = re.compile(r"^\s*(if|when|for\s+mixing)\b", re.IGNORECASE)

# A mix sub-group label: "For mixing Tanks 3 and 5:" / "To mix tank 1:" — a
# line that scopes the actions beneath it. Distinguished from a CONDITIONAL
# action by the trailing colon.
_GROUP_HEADER_RE = re.compile(r"^\s*(for\s+mixing|to\s+mix)\b.*:\s*$", re.IGNORECASE)

_NOTE_RE = re.compile(
	r"(confirm\s+in\s+plc|please\s+set\s+up|currently\s+each\s+chemical|"
	r"^\s*notes?\b)",
	re.IGNORECASE,
)

# Unambiguous spelling corrections only. Whole-word, case-insensitive. This set
# is deliberately tiny and conservative — anything semantic stays verbatim.
_TYPO_FIXES = {
	"substitue": "substitute",
	"refernce": "reference",
	"mintue": "minute",
	"mintues": "minutes",
}


@dataclass
class ClassifiedLine:
	raw: str                                              # original text, verbatim
	text: str                                             # display text (typos may be fixed)
	kind: LineType
	corrections: list[tuple[str, str]] = field(default_factory=list)  # (was, now)


def _clean_marks(line: str) -> str:
	"""Strip stray markdown-ish emphasis markers, leaving the plain text."""
	return line.strip().strip("*").strip()


def _apply_typo_fixes(text: str) -> tuple[str, list[tuple[str, str]]]:
	corrections: list[tuple[str, str]] = []
	out = text
	for wrong, right in _TYPO_FIXES.items():
		pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
		if pattern.search(out):
			out = pattern.sub(right, out)
			corrections.append((wrong, right))
	return out, corrections


def classify_line(raw: str) -> Optional[ClassifiedLine]:
	"""Classify one raw line. Returns None for blank/empty lines."""
	stripped = raw.strip()
	if not stripped:
		return None

	core = _clean_marks(stripped)
	if not core:
		return None

	display, corrections = _apply_typo_fixes(core)

	def make(kind: LineType) -> ClassifiedLine:
		return ClassifiedLine(raw=core, text=display, kind=kind, corrections=corrections)

	low = core.lower()

	# 1. Section title — the redundant restatement of the section heading.
	if re.search(r"step\s+by\s+step\s+sequence$", low):
		return make(LineType.SECTION_TITLE)

	# 2. Transition — the rule that ENDS a step. Checked early so it is never
	#    mistaken for a step header.
	if _TRANSITION_RE.match(core):
		return make(LineType.TRANSITION)

	# 3. Note / open question — customer questions and requests.
	if _NOTE_RE.search(core):
		return make(LineType.NOTE)

	# 4. Step header — a named phase: a known name, or a short Title-case line
	#    ending in ':' that is not itself an action.
	header_candidate = low.rstrip(":").strip()
	if header_candidate in _KNOWN_STEPS:
		return make(LineType.STEP_HEADER)
	if core.endswith(":") and len(core.split()) <= 4 and not _ACTION_VERB_RE.match(core):
		return make(LineType.STEP_HEADER)

	# 5. Mix sub-group label — "For mixing Tanks 3 and 5:". Must precede the
	#    conditional check, which would otherwise swallow "For mixing ...".
	if _GROUP_HEADER_RE.match(core):
		return make(LineType.GROUP_HEADER)

	# 6. Conditional action — gated on an if/when.
	if _CONDITIONAL_RE.match(core):
		return make(LineType.CONDITIONAL)

	# 7. Action — starts with an operational verb / device, OR is a "subject +
	#    state verb" sentence ("Tank valve, P1, P2 remain open").
	if _ACTION_VERB_RE.match(core):
		return make(LineType.ACTION)
	if _STATE_VERB_RE.match(core):
		return make(LineType.ACTION)
	if _DEVICE_SUBJECT_RE.match(core):
		return make(LineType.ACTION)

	# 8. Fallback — keep it, render it verbatim as prose.
	return make(LineType.PROSE)


def classify_lines(raw_lines: list[str]) -> list[ClassifiedLine]:
	out: list[ClassifiedLine] = []
	for ln in raw_lines:
		c = classify_line(ln)
		if c is not None:
			out.append(c)
	return out
