# craft × aizzz lane — the full chain struck once (2026-11-16T16:02Z)

One free-form Chinese requirement, one living model, the whole factory.

- requirement: `修复 double 函数的逻辑错误` (scratch python fixture, `calc.py` `double` returned `x / 2`)
- plan (`compile_plan(mode="llm")`): plan.mode=**llm** · fallback reason: **empty** · 4 Chinese steps (understand → modify → test → verify)
- loop (no injected fix rules; the model proposed the edit itself): LOOP_RESULT=**DONE** · the model's diff: `return x / 2` → `return x * 2`
- LLM stats (in-memory): calls=2 · prompt_tokens=10,553 · completion_tokens=1,435 · reasoning_tokens=1,010 · **prompt_cache_hit_tokens=4,224** (second call hit the resident prefix)
- verdict at the door (`craft_accept`, FAST, Docker gate): **BLOCKED** — for infrastructure, not for code:
  `run_test` gate, mode=docker, `python -m pytest -q` exited 1
  → `/usr/local/bin/python: No module named pytest`
  (the Docker python cache is flagged NOT VERIFIED upstream; the cache carries `/wheelhouse` but the invocation path never passed cache_dir+cache_manifest)
- fail-closed rollback worked as designed: HEAD is back on base (`9fcb754`), `calc.py` is `x / 2` again
- the other four gates: run_build passed · run_typecheck skipped (mypy unavailable, honest SKIPPED) · security passed · self_verify passed

**What this strike proves:** the aizzz lane is wired into the whole chain — planning, editing, reasoning.
**What it does not prove:** a green certificate. The door refused an imperfect room, and the book records the refusal, not a ceremony.
Not one threshold was moved to get past the gate. Not one byte was pledged to claim safety that a cache never earned.
