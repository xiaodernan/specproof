"""Operations tooling — recovery & security drill helpers (§12, DRILLS.md).

The helpers in this package are pure orchestration utilities used by the
drill drivers (scripts/drill_worker_kill.py, scripts/drill_outbox_crash.py)
and covered by tests/unit/test_drill_helpers.py. They never mutate anything
on their own: every effect goes through the real storage clients the caller
passes in.
"""
