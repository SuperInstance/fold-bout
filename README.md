# fold-bout

A judged head-to-head: **MiniMax vs Claude Code**, same brief, same repo.

The task (see TASK.md): implement `fold.py` — deterministic state
derivation over a task-completion record (the "fold problem" from the
git.pp / next-git research line). Properties P1–P6 in TASK.md are the
contract; `test_fold.py` checks them.

## Protocol
- Each contestant works on its own branch: `minimax/fold`, `claude/fold`.
- Deliverables on the branch: `fold.py` + `DESIGN.md` at repo root.
- Scoring: the property tests here, a second private stress set
  (random DAGs, permutation storms) run by the referee, a blind A/B
  read of the DESIGN.md files, and the referee's own review.
- Referee: Muse (SuperInstance), at the direction of Casey.

Tests: `python3 test_fold.py fold.py` from the branch checkout.
