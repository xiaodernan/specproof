# SpecProof / SpecCraft — AI Change Acceptance Firewall

SpecProof does two things: it lets AI modify code by demand, and it independently checks whether a change respects the demand (差分/变异/审计/证据链).

Spec is the requirement; Proof is the evidence.

Spec 是需求，Proof 是证据。 This file is a router for agents and new contributors; **authoritative documents** live in `README.md` and `docs/`, not here.

## Authoritative documents (start here) · 权威文档（从这里开始）

- `README.md` — product walk, how to run, acceptance criteria vocabulary (VERIFIED / BLOCKED / NEEDS_REVIEW / FAILED + row-level `UNVERIFIED`), the honesty-column rules.
  —— 产品走查、怎么跑、验收结论词表（VERIFIED / BLOCKED / NEEDS_REVIEW / FAILED，行级 UNVERIFIED）、诚实列的规矩。
- `docs/operations/PRODUCT_ROADMAP.md` — current priority, checked items with evidence.
  —— 当前优先级，以及每一件已勾选工作的证据。
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md` — the ledger (`## #NNN` per unit of work; verify with `tests/unit/test_recorded_ledger_sections_do_not_vanish.py`).
  —— 账本（每件工作一节 ## #NNN；用 tests/unit/test_recorded_ledger_sections_do_not_vanish.py 验它没消失）。
- `docs/architecture/ARCHITECTURE.md` · `docs/architecture/EXECUTION_COMPATIBILITY.md` · `docs/architecture/DATA_DICTIONARY.md` — design, language/toolchain support matrix, storage facts.
- `SECURITY.md` · `CONTRIBUTING.md` · `LICENSE` · `CHANGELOG.md` — trust model, contract, license, change shape.
  —— 信任模型、协作契约、许可证、改动形态。

## What the pipeline is · 这条流水线是什么

A 18-node LangGraph (`agent/graph.py`):
`intake → preflight → compile_contracts → contract_review → prepare_base → prepare_head → collect_diff → retrieve_repository_context → run_static_checks → generate_counterexamples → run_differential → run_deep_experiments → collect_evidence → review_court → create_capsule → build_matrix → run_release_checks → publish_report`

Diff execution runs **inside a sandbox** (uid 1000, `--network none`, read-only workspace, `--cap-drop ALL`, `--pids-limit 256`, `no-new-privileges`). The host never executes an untrusted repository's tests; Python requires `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1` explicitly.

Capability by language:

按语言的能力矩阵：

| Language | Real test lane | Sandbox surface |
|---|---|---|
| Java/Maven, Java/Gradle | `mvn`/`gradle` test, `SpecProofGeneratedTest` (Jit) | Docker digest-pinned (Gradle `sha256:963d59f7…` measured 2026-11-09) |
| Node/TS/JS | `node:test` (零依赖) · npm offline from seeded `node_modules` cache | `node:22-alpine`, μη-1 uid 1000 |
| Python | pytest (offline wheelhouse) | `python:3.12-slim`, uid 1000 |
| Go | `go test -json ./...`, `GOPROXY=off` | Alpine, offline module cache |
| Rust/Gradle-Edge/others | inspect `EXECUTION_COMPATIBILITY.md` | **Not yet green** — do not claim covered |

Every claim above is backed by a digest, a registry row, a matrix cell, or a unit test; the ledger holds each fact with commit references.

## Everyday commands · 日常命令

```bash
pip install -e ".[dev]"
python -m cli.specproof.main --help      # verify | eval | replay | craft | doctor | mcp | ops | ...
python -m cli.specproof.main doctor      # same probe the worker runs before a job
python -m cli.specproof.main eval --cases golden-cases --repo . --no-llm
```

- Tests (quick): `pytest tests/unit -m "not integration and not slow" -q` (~3 min) — **not** a substitute for CI.
  —— 快速测试（约 3 分钟）不能代替 CI 的完整门。
- Tests (CI merge gate): `pytest tests/unit tests/security tests/fault` — always the full suite.
- Isolation: `SPECPROOF_TEST_MYSQL_DATABASE=specproof_test2 pytest …` — never point tests at the product schema.
  —— 隔离：测试永远不要指向产品库。

## Hard rules (non-negotiable) · 硬规矩（不可协商）

1. Enforcement CLI output / summary claims — every "passes" is either (a) actually verified or (b) explicitly marked as not. No laundering.
   1. 执行 CLI 的输出 / 摘要里的断言——每一句「通过」要么真被验证过，要么被明确标记为「未验证」。不许洗白。
2. Never weaken/delete a gate to make CI green. Fix the underlying issue or fail honestly.
   2. 绝不为让 CI 变绿而弱化或删除任何门。修根因，或者诚实地失败。
3. No real secrets in tree (`.env.example` shows shape only; local `.env` ignored).
   3. 仓库里不放真密钥。
4. No execution of untrusted code on the host. Only the sandbox (or the opt-in Python lane).
   4. 不在宿主机上执行不可信代码。只在沙箱里（或显式开启的 Python 通道里）。
5. Environment + defaults + `.env.example` + the gate owning the knob move together.
   5. 环境变量、默认值、.env.example、以及拥有这个开关的门，必须一起动。
6. Decisions live in the ledger; a green suite with no account is as good as silence.
   6. 决策写在账本里；一套全绿却没有交代的测试，等同于沉默。
7. Certificate signing is wired through `evidence/signing.py` — **Ed25519** in-toto-style statements, fail-closed (无密钥即 ERROR); `craft/accept.py` honours the verdict. Revert either and the claim goes too.
   7. 证书签发走 evidence/signing.py——Ed25519 的 in-toto 式声明，fail-closed（无密钥即 ERROR）；craft/accept.py 认这个判决。回退任何一边，这句断言也就作废。

## For AI agents · 给 AI agent 的话

Being an agent reading this file: don't duplicate the docs — read them; run the suite fully before claiming green; name your sources; never edit under `tests/*` whose only job is to fail honestly; if you can't verify, say so and stop rather than improvise.
  作为读这份文件的 agent：不要复述文档——去读它们；声称全绿之前把整套门跑完；说出你的依据；绝不改动 tests/ 下那些「唯一职责就是诚实失败」的测试；验证不了就直说并停下，不要即兴发挥。
