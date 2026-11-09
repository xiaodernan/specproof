# SpecProof / SpecCraft — AI Change Acceptance Firewall

SpecProof does two things: it lets AI modify code by demand, and it independently checks whether a change respects the demand (差分/变异/审计/证据链).

Spec is the requirement; Proof is the evidence. This file is a router for agents and new contributors; **authoritative documents** live in `README.md` and `docs/`, not here.

## Authoritative documents (start here)

- `README.md` — product walk, how to run, acceptance criteria vocabulary (VERIFIED / BLOCKED / NEEDS_REVIEW / FAILED + row-level `UNVERIFIED`), the honesty-column rules.
- `docs/operations/PRODUCT_ROADMAP.md` — current priority, checked items with evidence.
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md` — the ledger (`## #NNN` per unit of work; verify with `tests/unit/test_recorded_ledger_sections_do_not_vanish.py`).
- `docs/architecture/ARCHITECTURE.md` · `docs/architecture/EXECUTION_COMPATIBILITY.md` · `docs/architecture/DATA_DICTIONARY.md` — design, language/toolchain support matrix, storage facts.
- `SECURITY.md` · `CONTRIBUTING.md` · `LICENSE` · `CHANGELOG.md` — trust model, contract, license, change shape.

## What the pipeline is

A 18-node LangGraph (`agent/graph.py`):
`intake → preflight → compile_contracts → contract_review → prepare_base → prepare_head → collect_diff → retrieve_repository_context → run_static_checks → generate_counterexamples → run_differential → run_deep_experiments → collect_evidence → review_court → create_capsule → build_matrix → run_release_checks → publish_report`

Diff execution runs **inside a sandbox** (uid 1000, `--network none`, read-only workspace, `--cap-drop ALL`, `--pids-limit 256`, `no-new-privileges`). The host never executes an untrusted repository's tests; Python requires `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1` explicitly.

Capability by language:

| Language | Real test lane | Sandbox surface |
|---|---|---|
| Java/Maven, Java/Gradle | `mvn`/`gradle` test, `SpecProofGeneratedTest` (Jit) | Docker digest-pinned (Gradle `sha256:963d59f7…` measured 2026-11-09) |
| Node/TS/JS | `node:test` (零依赖) · npm offline from seeded `node_modules` cache | `node:22-alpine`, μη-1 uid 1000 |
| Python | pytest (offline wheelhouse) | `python:3.12-slim`, uid 1000 |
| Go | `go test -json ./...`, `GOPROXY=off` | Alpine, offline module cache |
| Rust/Gradle-Edge/others | inspect `EXECUTION_COMPATIBILITY.md` | **Not yet green** — do not claim covered |

Every claim above is backed by a digest, a registry row, a matrix cell, or a unit test; the ledger holds each fact with commit references.

## Everyday commands

```bash
pip install -e ".[dev]"
python -m cli.specproof.main --help      # verify | eval | replay | craft | doctor | mcp | ops | ...
python -m cli.specproof.main doctor      # same probe the worker runs before a job
python -m cli.specproof.main eval --cases golden-cases --repo . --no-llm
```

- Tests (quick): `pytest tests/unit -m "not integration and not slow" -q` (~3 min) — **not** a substitute for CI.
- Tests (CI merge gate): `pytest tests/unit tests/security tests/fault` — always the full suite.
- Isolation: `SPECPROOF_TEST_MYSQL_DATABASE=specproof_test2 pytest …` — never point tests at the product schema.

## Hard rules (non-negotiable)

1. Enforcement CLI output / summary claims — every "passes" is either (a) actually verified or (b) explicitly marked as not. No laundering.
2. Never weaken/delete a gate to make CI green. Fix the underlying issue or fail honestly.
3. No real secrets in tree (`.env.example` shows shape only; local `.env` ignored).
4. No execution of untrusted code on the host. Only the sandbox (or the opt-in Python lane).
5. Environment + defaults + `.env.example` + the gate owning the knob move together.
6. Decisions live in the ledger; a green suite with no account is as good as silence.

## For AI agents

Being an agent reading this file: don't duplicate the docs — read them; run the suite fully before claiming green; name your sources; never edit under `tests/*` whose only job is to fail honestly; if you can't verify, say so and stop rather than improvise.
