"""Deterministic fold from a record of task completions to current state.

TIE-BREAK (P6): among applied records of the same class that set the same key
and where none is an ancestor of another, the record with the greater depth
(longest ancestry) wins, and if depths are equal the lexicographically smallest
record id wins.

RESOLUTION ORDER: witness humility, then ancestry, then class priority. P3 says
class priority "applies only when ancestry alone doesn't already decide (a
descendant beats its own ancestors for keys it sets)", so ancestry is reduced
FIRST and class priority only ever sees writes that ancestry left incomparable.
Witness humility is the one absolute rule: a witness never wins a key against a
task or an override, even when the witness is a descendant. Record kinds outside
{"task","witness","override"} are ranked as witnesses, because we cannot verify
that they carry intent.
"""

import heapq
import json

# Lower is stronger. Unknown kinds fall to the most humble class (see docstring).
CLASS_RANK = {"override": 0, "task": 1, "witness": 2}
_FALLBACK_RANK = 2


def _index(records):
    """id -> record, built in a canonical order so input permutation cannot matter."""
    ordered = sorted(
        records,
        key=lambda r: (str(r.get("id", "")), json.dumps(r, sort_keys=True, default=str)),
    )
    return {str(r["id"]): r for r in ordered}


def _parents(rec):
    return [str(p) for p in (rec.get("parents") or [])]


def _effects(rec):
    return {str(k): v for k, v in (rec.get("effects") or {}).items()}


def _rank(rec):
    return CLASS_RANK.get(rec.get("kind"), _FALLBACK_RANK)


def _cycle_affected(nodes, parents):
    """Nodes that cannot be topologically ordered (in, or blocked behind, a parent cycle)."""
    indeg = {r: 0 for r in nodes}
    children = {r: [] for r in nodes}
    for r in nodes:
        for p in parents[r]:
            if p in indeg:
                indeg[r] += 1
                children[p].append(r)
    ready = [r for r in nodes if indeg[r] == 0]
    heapq.heapify(ready)
    done = set()
    while ready:
        n = heapq.heappop(ready)
        done.add(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(ready, c)
    return set(nodes) - done


def _topological(nodes, parents):
    """Kahn's algorithm, always taking the smallest ready id: one canonical order."""
    indeg = {r: len(parents[r]) for r in nodes}
    children = {r: [] for r in nodes}
    for r in nodes:
        for p in parents[r]:
            if p in children:
                children[p].append(r)
    ready = [r for r in nodes if indeg[r] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(ready, c)
    return order


def derive(records):
    records = list(records)
    idx = _index(records)
    ids = set(idx)
    parents = {rid: _parents(rec) for rid, rec in idx.items()}

    children = {rid: [] for rid in idx}
    for rid, ps in parents.items():
        for p in ps:
            if p in children:
                children[p].append(rid)

    # Orphans: a record is orphaned if any ancestor is absent, or is itself already
    # orphaned. Propagated with a worklist (O(N+E)) rather than a repeated rescan,
    # which is quadratic when ids happen to sort dependants before their parents.
    orphan = set()
    work = [rid for rid in idx if any(p not in ids for p in parents[rid])]
    orphan.update(work)
    head = 0
    while head < len(work):
        for c in children[work[head]]:
            if c not in orphan:
                orphan.add(c)
                work.append(c)
        head += 1
    orphan |= _cycle_affected(set(ids) - orphan, parents)

    applied = sorted(set(idx) - orphan)
    applied_set = set(applied)
    order = _topological(applied, parents)

    depth = {}
    for rid in order:
        ps = parents[rid]
        depth[rid] = max((depth[p] for p in ps), default=-1) + 1

    # Who sets each key, among applied records only.
    setters = {}
    for rid in applied:
        for k in _effects(idx[rid]):
            setters.setdefault(k, set()).add(rid)

    state = {}
    conflicts = []
    for k in sorted(setters):
        cands = sorted(setters[k])
        # P3: "class priority is override > task > witness, applied ONLY when
        # ancestry alone doesn't already decide (a descendant beats its own
        # ancestors for keys it sets)".
        #
        # The order of the stages is therefore load-bearing, and getting it
        # wrong is invisible to a suite that only tests INCOMPARABLE
        # competitors. Three stages, in this order:
        #
        #   1. Witness humility. "A witness record never wins a key against a
        #      task or override record." Absolute: if any task or override set
        #      this key, witnesses are not candidates for it at all -- even a
        #      witness that descends from the task.
        #   2. Ancestry reduction. A candidate is dominated if it is an
        #      ANCESTOR of another candidate; the survivors are the
        #      most-derived. This is the stage that decides a descendant
        #      against its own ancestor, and it must come BEFORE class
        #      priority or a descendant task can never beat an ancestor
        #      override.
        #   3. Class priority, which now only ever sees writes that ancestry
        #      left incomparable.
        pool = set(cands)
        non_witness = [c for c in cands if idx[c].get("kind") != "witness"]
        if non_witness:
            pool = set(non_witness)
        # A candidate is dominated if it is an ANCESTOR of ANY other
        # candidate -- not merely of the nearest one. Walking up and
        # stopping at the first pool hit leaves a farther ancestor
        # undominated, and that farther ancestor can then win on class
        # priority: an override that is an ancestor of a candidate
        # through TWO hops used to survive as "maximal" and beat the
        # more-derived task that should have superseded it.
        #
        # `expanded` makes the walk amortised O(N+E) per key: a node
        # whose ancestor chain has already been walked is not walked
        # again. Its pool-ancestors are already in `dominated`.
        dominated = set()
        if len(pool) > 1:
            expanded = set()
            for d in sorted(pool):
                stack = list(parents[d])
                while stack:
                    x = stack.pop()
                    if x in pool:
                        dominated.add(x)
                    if x in expanded:
                        continue
                    expanded.add(x)
                    stack.extend(parents.get(x, ()))
        maximal = sorted(pool - dominated)
        if len(maximal) > 1:
            best = min(_rank(idx[c]) for c in maximal)
            maximal = [c for c in maximal if _rank(idx[c]) == best]
        winner = maximal[0] if len(maximal) == 1 else min(maximal, key=lambda c: (-depth[c], c))

        state[k] = _effects(idx[winner])[k]
        distinct = []
        for c in cands:
            v = _effects(idx[c])[k]
            if v not in distinct:
                distinct.append(v)
        if len(distinct) >= 2:
            conflicts.append(
                {"key": k, "winner": winner, "losers": sorted(c for c in cands if c != winner)}
            )

    return {"state": state, "order": order, "conflicts": conflicts, "orphans": sorted(orphan)}


def verify_checkpoint(records, checkpoint):
    """True only if deriving from exactly the ancestors of checkpoint['at'] (incl. it)
    reproduces checkpoint['state']. A missing 'at' record, or any missing ancestor
    (so the ancestor set is incomplete and nothing can be verified), returns False."""
    if not isinstance(checkpoint, dict):
        return False
    at, want = checkpoint.get("at"), checkpoint.get("state")
    if at is None or not isinstance(want, dict):
        return False
    at = str(at)

    idx = _index(records)
    if at not in idx:
        return False
    parents = {rid: _parents(rec) for rid, rec in idx.items()}

    closure, stack = set(), [at]
    while stack:
        n = stack.pop()
        if n in closure:
            continue
        closure.add(n)
        for p in parents.get(n, ()):
            if p not in idx:
                return False
            stack.append(p)

    return derive([idx[r] for r in sorted(closure)])["state"] == want
