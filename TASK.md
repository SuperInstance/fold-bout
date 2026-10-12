# Bout 1 — MiniMax vs Claude Code: the deterministic fold

Set up 2026-10-11 by Casey's direction ("Have MiniMax compete against
Claude Code. Let's see which one produces better results."). Identical
brief to both. Disclosed asymmetry: MiniMax has prior context (it
raised the fold problem in its red team and is separately writing a
test-suite spec for it); Claude gets everything it needs in the brief.
Claude's route is Casey's claude.ai Pro plan in the browser (one shot,
no iteration) — Claude is the scarce resource by standing policy; this
bout is Casey's explicit call.

## The brief (verbatim text sent to both)

You are competing in a judged head-to-head against another AI system.
Same brief, same deliverable, scored on working code and stated
reasoning. Context you need:

We are designing a system where the atom is the TASK and state is what
completed tasks leave behind. Completions are recorded as commits in a
record. Two rules govern everything: (1) PROVENANCE WINS — when two
valid versions disagree, the one with the cleanest intent/ancestry
chain ships by default; judges/tournaments are advisory only; losing
versions are preserved intact, never silently dropped. (2) A proposed
settlement of the "fold problem" (state derived from a series of
completions must not depend on the order concurrent agents happened
to finish in):
  a. The series is the ancestry chain in the record, not wall-clock
     order: every completion is a record whose parents are the state
     it completed against.
  b. Concurrent completions fork the chain; deriving state walks the
     DAG and applies the provenance rule deterministically — same
     record, same derived state, regardless of arrival order.
  c. Ambient change enters as a WITNESS record: observation without
     intent. The record distinguishes "done by us" from "seen by us".
  d. Checkpoints are legal only provenance-stamped: a checkpoint names
     the record position it summarises and its producing chain.

DELIVERABLE — one self-contained Python 3 file `fold.py` (standard
library only) implementing:

Records are dicts: {"id": str, "parents": [str, ...],
"kind": "task" | "witness" | "override",
"effects": {str: scalar}, "reason": str (optional, for overrides)}

Function derive(records) -> dict with keys:
  "state": the derived current state {key: value},
  "order": [record ids in the order you applied them],
  "conflicts": [{"key": k, "winner": record_id,
                 "losers": [record_id, ...]}, ...] for every key where
                 applied records disagreed,
  "orphans": [record ids excluded because an ancestor is missing].

Required properties (hidden tests will check exactly these):
  P1 Determinism: any permutation of the input list yields an
     identical output dict.
  P2 Ancestry: in "order", every record appears after all of its
     parents. A record with any missing ancestor (transitively) is an
     orphan: excluded from "order" and from state, listed in "orphans".
  P3 Witness humility: a witness record never wins a key against a
     task or override record. Among candidates for a key, class
     priority is override > task > witness, applied only when ancestry
     alone doesn't already decide (a descendant beats its own
     ancestors for keys it sets).
  P4 Override inheritance: if record X sets key K, and a later
     (descendant) override record O also sets K, O wins; and any
     record descending from O sees O's value as the one to beat.
  P5 Loser preservation: every applied record that set a contested key
     and lost appears in that key's "losers". Nothing is dropped
     silently. Winners are the records whose value is in "state".
  P6 Your tie-break: for two incomparable records (neither is the
     other's ancestor) of the same class setting the same key, define
     a deterministic rule, implement it, and state it in one sentence
     in a module docstring. Permutation-invariance must hold.

Function verify_checkpoint(records, checkpoint) -> bool, where
checkpoint = {"at": record_id, "state": {...}}: return True only if
deriving state from exactly the ancestors of "at" (including "at")
reproduces checkpoint["state"] exactly. A checkpoint claiming a state
that derivation does not produce — or naming a missing record — must
return False.

Also deliver DESIGN.md (short): your tie-break rule, how your
derivation guarantees P1, where the design would break at 10,000
records, and one thing you chose NOT to do and why.

Return fold.py in full and DESIGN.md in full, as text. No placeholders,
no ellipses — runnable code only.
