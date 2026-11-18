# Ask the Book · live strike evidence — 2026-11-18

**Live strikes through the running FastAPI app (`api.server:app` on `127.0.0.1:8031`, aizzz `gpt-6.1-terra`, protocol=`responses`, `stream=True`, `include_usage=True`, proxy=Clash Verge `http://127.0.0.1:7897`).**

This file is captured by running the real lane — not by hand, not by constructing fake responses. It is the first time the `/worldbook/ask` lane was struck end-to-end against the live model; nothing here is edited.

## Strike 1

- **Question** (zh, 12 CJK chars):「这个世界书从哪一卷开始？」
- **Answer** (verbatim from the model):「从卷零《创世之炉》开始。」
- **Model**: `gpt-6.1-terra`
- **Latency**: 11,716 ms
- **Usage**: `prompt_tokens=167,470 · completion_tokens=235 · reasoning_tokens=218 · prompt_cache_hit_tokens=7,974 · prompt_cache_miss_tokens=159,496`
- **Cached**: `cached=false` — **first strike ever for this lane**: the `specproof-worldbook-ask` cache slot was being written, not read. That is honest, not a failure.

## Strike 2 — identical question back-to-back

- **Cached**: `cached=true`
- **Usage**: identical to Strike 1 (same fingerprinted prompt → same cached answer, zero model call)

## Strike 3 — different question, warm slot

- **Question** (zh, 14 CJK chars):「Court 为什么永远锁着？」
- **Answer** (verbatim):「这里的“锁着”不是法庭停用，而是它的裁决边界被机器固定住了：审判庭相关证据永不进入语义缓存，必须依据当次证据判断；模型只能提供说明，不能替人裁决或签收。缓存可能让旧结果冒充新证据，因此不能用速度换裁决的可靠性。卷七十七记载，`audit_court_lock.py` 会核对五项关键约束：流式请求、用量回传、策略开关，以及证据类与可缓存类的精确名单。任何一项漂移，锁就会报坏；当前锁值为 `4117d2b0ca5fb23a`。所以它“永远锁着”的意思是这条边界不因便利而放宽，不是法庭不能工作。」
- **Model**: `gpt-6.1-terra`
- **Latency**: 15,561 ms
- **Usage**: `prompt_tokens=167,468 · completion_tokens=616 · reasoning_tokens=424 · prompt_cache_hit_tokens=157,366 · prompt_cache_miss_tokens=10,102` — **93.9% cached**
- **Cached**: `cached=false` (fresh question text, warm prefix re-used — exactly the design)

## What this proves

1. The whole 167 KB world book is riding as the codex prefix with one `sticky prompt_cache_key=specproof-worldbook-ask` — one sticky lane, same shape as `/zeal`/codex lanes.
2. The model knows the book in depth: correct citation of scroll LXXVII conventions, `audit_court_lock.py`'s five-point lock check, lock hash `4117d2b0ca5fb23a` — all real, verifiable.
3. The cache behavior is correct by construction: first strike writes, second returns fingerprint hit without a model call, different question rides the warm prefix at 94% hit rate.
4. The model honours the verdict-free rules — it explains the court, it does not rule for anyone.

Court `4117d2b0ca5fb23a` LOCKED · Night Watch CRACKED · exhibit_entries 18 · 24 pinned reds.
