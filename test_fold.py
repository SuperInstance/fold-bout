#!/usr/bin/env python3
"""Hidden property tests for Bout 1 (written before submissions arrived).

Usage: python3 test_fold.py /path/to/fold.py
Scores P1..P6 + checkpoint honesty. Design-freedom note: for P6
incomparable same-class conflicts we do NOT assert which record wins —
only determinism (P1 covers it) and loser preservation (P5).
"""
import importlib.util, itertools, random, sys

def load(path):
    spec = importlib.util.spec_from_file_location("fold_sub", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def R(id, parents, kind, effects, **kw):
    d = {"id": id, "parents": parents, "kind": kind, "effects": effects}
    d.update(kw)
    return d

results = []
def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print(f"PASS {name}")
    except Exception as e:
        results.append((name, False, repr(e)))
        print(f"FAIL {name}: {e!r}")

def main():
    mod = load(sys.argv[1])
    derive, verify = mod.derive, mod.verify_checkpoint

    base = [
        R("a", [], "task", {"x": 1, "shared": "a"}),
        R("b", ["a"], "task", {"y": 2, "shared": "b"}),
        R("c", ["a"], "task", {"z": 3, "shared": "c"}),   # incomparable with b
        R("w", ["b"], "witness", {"y": 99, "seen": True}), # witness must not beat b on y
        R("o", ["c"], "override", {"shared": "o"}, reason="captain said so"),
        R("d", ["b", "o"], "task", {"w2": 1}),
    ]

    def p1():
        ref = derive([dict(r) for r in base])
        rng = random.Random(42)
        for _ in range(60):
            perm = [dict(r) for r in base]
            rng.shuffle(perm)
            assert derive(perm) == ref, "permutation changed output"
    check("P1 determinism under permutation", p1)

    def p2():
        out = derive([dict(r) for r in base])
        pos = {rid: i for i, rid in enumerate(out["order"])}
        for r in base:
            for p in r["parents"]:
                assert pos[p] < pos[r["id"]], f"{p} not before {r['id']}"
        ghost = base + [R("g", ["missing"], "task", {"x": 5}),
                        R("h", ["g"], "task", {"x": 6})]
        out2 = derive([dict(r) for r in ghost])
        assert set(out2["orphans"]) == {"g", "h"}, out2["orphans"]
        assert "g" not in out2["order"] and "h" not in out2["order"]
    check("P2 ancestry order + orphan exclusion", p2)

    def p3():
        out = derive([dict(r) for r in base])
        assert out["state"]["y"] == 2, "witness overwrote a task value"
        assert out["state"].get("seen") is True, "witness-only key missing"
    check("P3 witness humility", p3)

    def p4():
        # override on one branch vs task on an incomparable sibling branch:
        # class priority (override > task) must decide; descendants of the
        # override inherit its value as state.
        recs = [R("r", [], "task", {"k": "base"}),
                R("t", ["r"], "task", {"k": "taskval"}),
                R("o", ["t"], "override", {"k": "over"}, reason="because"),
                R("s", ["t"], "task", {"k": "sib"}),
                R("g", ["o", "s"], "task", {"other": 1})]
        out = derive([dict(x) for x in recs])
        assert out["state"]["k"] == "over", f"override lost: {out['state']}"
    check("P4 override inheritance + class priority", p4)

    def p5():
        out = derive([dict(r) for r in base])
        entries = [c for c in out["conflicts"] if c["key"] == "shared"]
        assert entries, "shared conflict not reported"
        all_losers = set()
        for e in entries:
            all_losers |= set(e["losers"])
        vals = {r["id"]: r["effects"].get("shared") for r in base}
        winner = [rid for rid, v in vals.items()
                  if v == out["state"]["shared"] and rid in vals]
        assert winner, "state value matches no setter"
        w = winner[0]
        setters = {"a", "b", "c", "o"}
        assert setters - {w} <= all_losers, \
            f"missing losers: {setters - {w} - all_losers}"
    check("P5 loser preservation", p5)

    def p6():
        # same-class incomparable conflict: deterministic across perms
        pair = [R("r", [], "task", {}),
                R("m", ["r"], "task", {"k": "m"}),
                R("n", ["r"], "task", {"k": "n"})]
        outs = set()
        for perm in itertools.permutations(pair):
            o = derive([dict(x) for x in perm])
            outs.add((o["state"]["k"], tuple(sorted(o["order"]))))
        assert len(outs) == 1, f"tie-break not deterministic: {outs}"
    check("P6 deterministic tie-break", p6)

    def ckpt():
        out = derive([dict(r) for r in base])
        # honest checkpoint at b: state from ancestors of b = a,b
        sub = derive([dict(r) for r in base[:2]])
        assert verify([dict(r) for r in base],
                      {"at": "b", "state": sub["state"]}) is True
        # forged: tampered value
        bad = dict(sub["state"]); bad["y"] = 777
        assert verify([dict(r) for r in base],
                      {"at": "b", "state": bad}) is False
        # missing record
        assert verify([dict(r) for r in base],
                      {"at": "nope", "state": {}}) is False
    check("checkpoint verify honest/forged/missing", ckpt)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\nSCORE {passed}/{len(results)}")

if __name__ == "__main__":
    main()
