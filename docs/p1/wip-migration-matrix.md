# P1 WIP Migration Matrix

Source: `D:/experim/specproof-phase0` (master branch, dirty worktree)

## Summary

The master worktree contains ~20 modified files and ~15 untracked files representing
incomplete P1.1–P1.7 implementation. This matrix classifies each file for selective
migration into the clean `feature/p1-reliability-kernel` branch (based on `p0.5-verified-v1`).

## Migration Rules

1. No wholesale copy — each file evaluated individually
2. P1-A batch only migrates P1.1–P1.4 items
3. P1.5–P1.7 items documented but NOT migrated
4. Mixed files (touching both P1-A and later phases) are split by hunk
5. All migrated code must pass existing P0.5 tests

## File Matrix

### Modified Files (tracked, unstaged changes)

| File | P1 Task | Verdict | Reason | Risk | Tests Needed |
|------|---------|---------|--------|------|-------------|
| `storage/mysql.py` | P1.1, P1.2 | **Partial reuse** | Contains state machine transitions, outbox DDL, `transition_job_status()`, `create_job_with_outbox()`. Rewrite cleanly using same design. | Must not break existing P0.5 tables | unit + integration |
| `storage/rabbitmq.py` | P1.3 | **Partial reuse** | Contains DLQ topology, retry logic, Manual Ack patterns. Rewrite with idempotency. | Publisher Confirm already works in P0.5 | unit + integration |
| `storage/redis.py` | P1.4 | **Partial reuse** | Contains Stream ops, lock, budget keys. Rewrite with SSE support. | Existing lock/cache must still work | unit + integration |
| `pyproject.toml` | P1.0 | **Partial reuse** | Adds `fastapi`, `uvicorn`, `opentelemetry-*` deps. Only add what P1-A needs. | Dependency conflicts | integration |
| `agent/graph.py` | P1.6 | **DEFER to P1-B** | LangGraph checkpoint support | Not in P1-A scope | — |
| `agent/nodes/create_capsule.py` | P1.5 | **DEFER to P1-B** | MongoDB/MinIO artifact writes | Not in P1-A scope | — |
| `agent/nodes/generate_counterexamples.py` | P1.6 | **DEFER to P1-B** | Checkpoint-aware execution | Not in P1-A scope | — |
| `agent/nodes/review_court.py` | P1.6 | **DEFER to P1-B** | Checkpoint-aware execution | Not in P1-A scope | — |
| `agent/nodes/run_differential.py` | P1.6 | **DEFER to P1-B** | Worker integration | Not in P1-A scope | — |
| `agent/nodes/run_static_checks.py` | P1.6 | **DEFER to P1-B** | Worker integration | Not in P1-A scope | — |
| `storage/minio.py` | P1.5 | **DEFER to P1-B** | MinIO artifact consistency | Not in P1-A scope | — |
| `storage/mongodb.py` | P1.5 | **DEFER to P1-B** | MongoDB evidence packs | Not in P1-A scope | — |
| `demo/spring-backend/**` | — | **DISCARD** | Demo repo changes unrelated to P1 | P0.5 demo is frozen | — |
| `tests/integration/test_differential.py` | P1.0 | **Partial reuse** | Test fixture adjustments. Merge compatible changes only. | Must not regress P0.5 | existing |

### Untracked Files (new, never committed)

| File | P1 Task | Verdict | Reason | Risk | Tests Needed |
|------|---------|---------|--------|------|-------------|
| `agent/worker.py` | P1.6 | **DEFER to P1-B** | LangGraph worker main | Depends on checkpoint | — |
| `agent/mongo_saver.py` | P1.6 | **DEFER to P1-B** | MongoDB checkpoint saver | Not in P1-A scope | — |
| `api/` | P1.4 | **Rewite** | FastAPI routes exist but tied to P1.5/P1.6 state shapes. Rewrite for P1-A scope. | SSE contract must be stable | unit + integration |
| `artifacts/` | — | **DISCARD** | Already migrated to P0.5 release | — | — |
| `agent/preflight.py` | — | **DISCARD** | Already in P0.5 release | — | — |
| `agent/security_scanner.py` | — | **DISCARD** | Already in P0.5 release | — | — |

## Migration Plan for P1-A

### Phase 1: Infrastructure (migrate first)
1. Extract state machine constants and `InvalidStateTransition` from WIP `mysql.py`
2. Extract outbox DDL and `create_job_with_outbox()` pattern from WIP
3. Extract RabbitMQ topology and retry patterns from WIP `rabbitmq.py`
4. Extract Redis key designs from WIP `redis.py`
5. Adapt `pyproject.toml` dependency additions

### Phase 2: New implementation (rewrite cleanly)
6. `storage/mysql.py` — write clean state machine + outbox (P1.1 + P1.2)
7. `storage/rabbitmq.py` — write clean DLQ + idempotency (P1.3)
8. `storage/redis.py` — write clean lock/budget/stream (P1.4)
9. `api/` — write clean FastAPI + SSE (P1.4)
10. `agent/worker.py` — minimal worker (only P1-A scope)

### Phase 3: Testing
11. Unit tests for each module
12. Integration tests with Docker containers
13. Fault injection tests

## Files NOT Migrated (P1-B or later)

See DEFER entries above. These will be addressed in a future batch after P1-A is merged.

## Existing P1 Design Documents

- `.claude/plans/bright-kindling-fairy.md` — full P1 architecture plan (reference only, do not copy)
- `.claude/tasks/current-context.md` — task tracking from prior sessions
