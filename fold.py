"""fold.py -- deterministic state derivation over a task-completion DAG.

Records are completions in a provenance record. ``derive`` walks the DAG (not
wall-clock order) and resolves every key the same way regardless of the order
records arrive in, honouring provenance (a descendant beats its own ancestors),
witness humility (observation never beats intent), and override inheritance.

P6 tie-break: among same-class records that are mutually incomparable in the
ancestry DAG and set the same key, the winner is the one with the most
transitive ancestors (the longer provenance chain), and any remaining tie is
broken by the lexicographically smallest record id.

Public API:
    derive(records) -> {"state", "order", "conflicts", "orphans"}
    verify_checkpoint(records, checkpoint) -> bool

Standard library only.
"""

import heapq
from collections import defaultdict

# Class priority used only to settle keys that ancestry alone leaves tied:
# override > task > witness. A witness never wins against a non-witness.
_CLASS_RANK = {"override": 2, "task": 1, "witness": 0}


def _dedupe(seq):
    """Order-preserving de-duplication of an id sequence."""
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _analyze(records):
    """Structural pass over the record set.

    Returns (by_id, order, orphans, ancestors):
      by_id     id -> record dict
      order     valid record ids in a canonical topological order
      orphans   sorted ids excluded because an ancestor is missing
      ancestors id -> set of its transitive ancestor ids (valid ids only)
    """
    by_id = {}
    for r in records:
        by_id[r["id"]] = r  # ids are assumed unique; last write wins defensively
    all_ids = set(by_id)
    parents = {rid: _dedupe(list(by_id[rid].get("parents", []))) for rid in all_ids}

    # 1. Orphans: any record pointing at a missing parent, plus every descendant.
    children = {rid: [] for rid in all_ids}
    tainted = set()
    for rid in all_ids:
        for p in parents[rid]:
            if p in all_ids:
                children[p].append(rid)
            else:
                tainted.add(rid)
    stack = list(tainted)
    while stack:
        cur = stack.pop()
        for ch in children[cur]:
            if ch not in tainted:
                tainted.add(ch)
                stack.append(ch)
    valid = all_ids - tainted

    # 2. Canonical topological order over valid records: Kahn's algorithm with
    #    an id-ordered ready queue, so the result depends only on the DAG, never
    #    on input order (P1, P2). Every parent of a valid record is itself valid.
    indeg = {rid: 0 for rid in valid}
    vchildren = {rid: [] for rid in valid}
    for rid in valid:
        for p in parents[rid]:
            indeg[rid] += 1
            vchildren[p].append(rid)
    ready = [rid for rid in valid if indeg[rid] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        cur = heapq.heappop(ready)
        order.append(cur)
        for ch in sorted(vchildren[cur]):
            indeg[ch] -= 1
            if indeg[ch] == 0:
                heapq.heappush(ready, ch)
    # Any valid record left out here sits in a cycle (not a DAG); it is excluded
    # from order and state rather than invented into existence.
    in_order = set(order)

    # 3. Transitive ancestors, built in topological order so parents are ready.
    ancestors = {}
    for rid in order:
        acc = set()
        for p in parents[rid]:
            if p in in_order:
                acc.add(p)
                acc |= ancestors[p]
        ancestors[rid] = acc

    return by_id, order, sorted(tainted), ancestors


def derive(records):
    """Derive current state from a record DAG.

    Returns a dict with keys ``state``, ``order``, ``conflicts``, ``orphans``.
    The output is identical for any permutation of ``records`` (P1).
    """
    by_id, order, orphans, ancestors = _analyze(records)

    def kind_of(rid):
        return by_id[rid].get("kind")

    def dominates(desc, anc):
        """Does descendant ``desc`` supersede ancestor ``anc`` on its lineage?

        Yes, unless ``desc`` is a mere witness and ``anc`` carries intent -- a
        witness never overwrites a task or override value (P3).
        """
        return not (kind_of(desc) == "witness" and kind_of(anc) != "witness")

    # Collect, per key, the applied records that set it (in topological order).
    setters = defaultdict(list)
    for rid in order:
        for key in by_id[rid].get("effects", {}):
            setters[key].append(rid)

    state = {}
    conflicts = []
    for key in sorted(setters):
        ids = setters[key]

        # Candidates = records not superseded by a dominating descendant that
        # also sets this key. This collapses each lineage to its frontier value
        # (descendant beats ancestor) while letting witnesses be passed over.
        candidates = []
        for x in ids:
            if not any(x != y and x in ancestors[y] and dominates(y, x) for y in ids):
                candidates.append(x)

        # Class priority settles incomparable frontier values; the tie-break
        # settles same-class incomparable ones (P6). Candidates sharing a class
        # are provably pairwise incomparable, so the tie-break only ever runs on
        # genuinely concurrent writes.
        top_rank = max(_CLASS_RANK[kind_of(c)] for c in candidates)
        top = [c for c in candidates if _CLASS_RANK[kind_of(c)] == top_rank]
        winner = sorted(top, key=lambda c: (-len(ancestors[c]), c))[0]

        state[key] = by_id[winner]["effects"][key]

        # Report a conflict for every key whose applied records disagreed, and
        # preserve every losing setter -- nothing is dropped silently (P5).
        values = {by_id[r]["effects"][key] for r in ids}
        if len(ids) >= 2 and len(values) >= 2:
            losers = sorted(r for r in ids if r != winner)
            conflicts.append({"key": key, "winner": winner, "losers": losers})

    return {
        "state": state,
        "order": order,
        "conflicts": conflicts,
        "orphans": orphans,
    }


def verify_checkpoint(records, checkpoint):
    """Return True only if the checkpoint is provenance-honest.

    Deriving state from exactly ``checkpoint["at"]`` and its ancestors must
    reproduce ``checkpoint["state"]`` exactly. A checkpoint naming a missing
    record, or claiming a state derivation does not produce, returns False.
    """
    at = checkpoint.get("at")
    by_id = {r["id"]: r for r in records}
    if at not in by_id:
        return False

    # Closure of ``at`` over its (existing) ancestors, including ``at`` itself.
    subset_ids = set()
    stack = [at]
    while stack:
        cur = stack.pop()
        if cur in subset_ids or cur not in by_id:
            continue
        subset_ids.add(cur)
        stack.extend(by_id[cur].get("parents", []))

    subset = [by_id[rid] for rid in subset_ids]
    return derive(subset)["state"] == checkpoint.get("state")
