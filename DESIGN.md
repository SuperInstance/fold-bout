# DESIGN — the deterministic fold

## Two readings of the brief (P2, P3–P4)

`TASK.md` fixes two points that a reader should know are deliberate choices,
because a different substrate could reasonably decide them the other way:

- **Orphans are transitive (P2).** "Any missing ancestor (transitively) is an
  orphan." A record whose parent is itself an orphan therefore has a missing
  *ancestor* and is excluded too, and `test_fold.py`'s `p2` pins exactly this
  (ghost `g` and its child `h` are both orphans). A non-transitive reading —
  keep an orphan's orderable descendants and "fold on what stands" — is also
  defensible, but it is a different fold; this entry implements the brief's.
- **Class precedence is ancestry-first (P3–P4).** A descendant beats its own
  ancestors for keys it sets; class priority (`override > task > witness`)
  decides only writes that ancestry leaves *incomparable*. So a descendant task
  supersedes an ancestor override on the same key, and a descendant witness
  never beats an ancestor task (witness humility holds regardless). An
  *absolute* class precedence — override always outranks task, even a task that
  descends from it — is the alternative reading; it, too, is a different fold.

Both are read straight off the brief's wording; neither is an accident of the
implementation, and switching either would change observable output.

## Tie-break rule (P6)

When two records of the **same class** set the same key and neither is an
ancestor of the other (genuinely concurrent writes), the winner is the record
with the **most transitive ancestors** — the longer provenance chain, i.e. the
one built on strictly more completed work — and any remaining tie is broken by
the **lexicographically smallest record id**.

Concurrency here is real: nothing in the DAG orders these two completions, so
any choice of winner is, honestly, arbitrary. The rule therefore optimises for
two things only — being *principled* (prefer the more-grounded chain, in the
spirit of "provenance wins") and being *total* (ancestor-count can tie, so the
id, the single permutation-invariant handle each record carries, is the final
arbiter). The loser is never discarded: it is recorded in `conflicts`, so the
arbitrariness is auditable rather than silent.

## How derivation guarantees P1 (determinism under permutation)

Every part of the output is a pure function of the DAG, never of input order:

1. **Topological order** is produced by Kahn's algorithm with an *id-ordered*
   ready queue (a heap). At each step the lowest-id unblocked record is emitted,
   so the sequence is uniquely determined by the edge set, not by how the list
   was shuffled. This single canonical order drives everything downstream.
2. **Winners** are chosen by a frontier reduction: a record is dropped if a
   dominating descendant also sets the key (collapsing each lineage to its tip),
   then class priority (`override > task > witness`) and the tie-break pick among
   the survivors. All three inputs — ancestry sets, class, ancestor-count+id —
   are structural, so the winner is identical under any permutation.
3. **Ordering of the containers themselves**: `conflicts` is emitted in sorted
   key order with `losers` sorted by id; `orphans` is sorted. `state` is a dict,
   compared order-insensitively. Hence `derive(perm) == derive(ref)` as a dict.

Witness humility and override inheritance fall out of the same frontier pass: a
witness descendant is *not* allowed to dominate a task/override ancestor, so
intent is never overwritten by observation; and because a descendant dominates
its own-class ancestors, a later override supersedes earlier writes on its chain
and is itself the value its descendants inherit.

## Where this breaks at 10,000 records

Correctness holds, but cost does not. The frontier step is **O(S²)** per key,
where S is the number of records setting that key, and it materialises a
**full transitive-ancestor set per record** (`ancestors[rid]`), which is
O(V·E) time and up to O(V²) memory. On a 10k-record DAG where many records
touch a hot key, both the per-key quadratic scan and the ancestor-set storage
blow up. The fix is not deployed here (see below): replace explicit ancestor
sets with on-the-fly reachability using the topological index (a descendant has
a strictly higher index), and fold each key in one left-to-right pass over
`order`, keeping only the current per-lineage frontier instead of comparing all
setters pairwise. That restores near-linear behaviour without changing a single
result.

## One thing I chose NOT to do, and why

I did **not** index ancestry for scale (interval labelling / bitset reachability
and the single-pass per-key fold described above). The brief asks for a correct,
self-contained, fully-stated settlement of the fold problem and tests it on small
DAGs; a clever reachability index would add real surface area (another structure
to keep provenance-honest under permutation) for performance the contract never
exercises. Keeping the derivation a plain, auditable frontier reduction makes the
determinism and provenance guarantees easy to read and verify by eye — which, for
a provenance-first system where *why a version won* must be inspectable, is worth
more than constant factors. The scaling path is written down above so the choice
is deferral, not omission.
