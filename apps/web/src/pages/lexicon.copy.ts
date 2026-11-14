import type { Locale } from "../i18n/strings";

/**
 * The Iron Lexicon in the app — the same 14 entries that live in
 * `docs/world/APPENDIX_IRON_LEXICON.md`, bilingual, tap-to-expand.
 * Every anchor is a real place in this repository; nothing here is lore.
 */

export interface LexiconEntry {
  /** The term, exactly as it appears in code / docs. */
  term: string;
  /** Short gloss in the ACTIVE language (one line). */
  gloss: Record<Locale, string>;
  /** The iron line — why this entry earned a place (two sentences max). */
  iron: Record<Locale, string>;
  /** Where to look in the repository. */
  anchor: string;
}

export const LEXICON: LexiconEntry[] = [
  {
    term: "accept_judge",
    gloss: { zh: "接受审判", en: "accept the verdict" },
    iron: {
      zh: "`accept.py` 里的裁决动作编码名——不可缓存的一类 evidence 动作，它的存在证明判决书已经落地。",
      en: "The code name of the verdict action in `accept.py` — a non-cacheable evidence action; its existence proves the certificate has landed.",
    },
    anchor: "providers/semantic_cache.py · docs/operations/DEEP_OPTIMIZATION_PLAN.md",
  },
  {
    term: "AUTH-01",
    gloss: { zh: "权限系列契约之一", en: "one of the AUTH contract family" },
    iron: {
      zh: "demo repo 的 `changeEmail` 需求化表达：未认证请求应被拒绝（401/403）且数据库行不变；checker_type=`http`。tag `head-v1` 移除 @PreAuthorize，差分必出 base_pass_head_fail。",
      en: "The demo repo's `changeEmail` requirement: an unauthenticated request must be rejected (401/403) with the database row unchanged; checker_type=`http`. Tag `head-v1` removes @PreAuthorize — the differential must yield base_pass_head_fail.",
    },
    anchor: "tests/integration/test_differential.py · demo/spring-backend (tag head-v1)",
  },
  {
    term: "capsule",
    gloss: { zh: "复现包（便携真相）", en: "bug capsule (portable truth)" },
    iron: {
      zh: "每次验收完成后，`create_capsule` 把结论、证据、执行环境、commit hash 压成一枚 `<job_id>.zip`——任何第三方全量重放都能看到同一个 finding。",
      en: "After every verification, `create_capsule` packs the verdict, the evidence, the execution environment and the commit hash into a `<job_id>.zip` — any third party replaying it sees the same finding.",
    },
    anchor: "agent/nodes/create_capsule.py · #/jobs/{id} → Findings",
  },
  {
    term: "counterexample_test",
    gloss: { zh: "反例测试（为验收官服务）", en: "counterexample test (for the officer)" },
    iron: {
      zh: "`generate_counterexamples.py` 按需求生成：base_pass_head_fail 的反例在 head 失败、在 base 通过——它是判决真假的唯一试金石。",
      en: "`generate_counterexamples.py` generates it from the requirement: for base_pass_head_fail the counterexample FAILS on head and PASSES on base — the only touchstone of a true verdict.",
    },
    anchor: "agent/nodes/generate_counterexamples.py",
  },
  {
    term: "differential execution",
    gloss: { zh: "差分执行", en: "differential execution" },
    iron: {
      zh: "base 与 head 编译进同一个沙箱，同一套测试依次跑过，看结论往哪边倒——倒的方向就是反例。`base_pass_head_fail` 是唯一被冠以「铁」的证据等级。",
      en: "base and head compile into one sandbox; the same test suite runs in both; the direction the verdict tips is the counterexample. `base_pass_head_fail` is the only evidence grade crowned with 「iron」.",
    },
    anchor: "docker_sandbox.py · tests/integration/",
  },
  {
    term: "execution_surface",
    gloss: { zh: "执行面（证据在哪跑出来）", en: "where the evidence ran" },
    iron: {
      zh: "`sandbox`（Docker 隔离）/ `host`（宿主降级，须标注）/ `none`（铁证缺失，矩阵标 UNVERIFIED）。每个 finding 强制携带——缺了它，就是隐瞒证据。",
      en: "`sandbox` (Docker-isolated) / `host` (degraded, must be labelled) / `none` (no iron evidence, matrix marks UNVERIFIED). Carried on every finding — missing it is concealment of evidence.",
    },
    anchor: "integrations/rollup_differential · tests/unit/test_matrix_pure.py",
  },
  {
    term: "findings_court_*",
    gloss: { zh: "审判庭指标家族", en: "review-court metric family" },
    iron: {
      zh: "observability 里针对裁决的一族 Prometheus 指标：开庭就 incr('findings_court_candidates_total')，裁决结果打到 findings_court_{final_status}_total。parity 测试钉住一行动一条指标的对应关系。",
      en: "A family of Prometheus metrics for verdicts: every sitting increments findings_court_candidates_total; results land on findings_court_{final_status}_total. A parity test pins one action to one metric.",
    },
    anchor: "agent/nodes/review_court.py · tests/unit/test_observability_metric_parity.py",
  },
  {
    term: "gate",
    gloss: { zh: "门（测试就是钉子）", en: "a gate (a test is a nail)" },
    iron: {
      zh: "门开了才进：`tests/unit/*`、`tests/e2e/*`、`tests/integration/*`——一次红就是一根钉子打进去；红了几例、少了哪一根，都写进账本。",
      en: "The gate opens before you pass: `tests/unit/*`, `tests/e2e/*`, `tests/integration/*` — every red nail is driven in and written into the ledger: how many red nails there are, and which one was pulled.",
    },
    anchor: "tests/ · docs/operations/DEEP_OPTIMIZATION_PLAN.md",
  },
  {
    term: "JUNIT_GENERATION_PROMPT",
    gloss: { zh: "反例生成 prompt 的稳定前缀", en: "the stable prefix of the counterexample prompt" },
    iron: {
      zh: "270 字符 / ~567 tokens 的不变前缀，先稳定、后变量——正是为了让 wkapi 的 prefix-cache 每次命中。该常数在 `_JUNIT_GENERATION_PROMPT`，不改变 ⇒ 缓存一直命中 ⇒ 成本持续下降。",
      en: "A ~567-token constant prefix, stable first and variable later — exactly so wkapi's prefix cache hits every time. The constant lives in `_JUNIT_GENERATION_PROMPT`; keep it unchanged and the cache keeps hitting.",
    },
    anchor: "providers/openai_compatible.py · scripts/probe_cache_efficiency.py",
  },
  {
    term: "ledger",
    gloss: { zh: "史官账本（DEEP_OPTIMIZATION_PLAN.md）", en: "the chronicler's ledger" },
    iron: {
      zh: "从 #1620 起（当前 #1697），每一条记：承诺的事、真实做了的事、剩余风险、证据、下一步——不允许假装完成，也不允许假装没事发生。本项目的心脏。",
      en: "From #1620 to today (#1697): every entry records what was promised, what was actually done, the residual risk, the evidence, and the next step — no pretending done, no pretending nothing happened. The heart of this project.",
    },
    anchor: "docs/operations/DEEP_OPTIMIZATION_PLAN.md",
  },
  {
    term: "matrix",
    gloss: { zh: "矩阵（需求 × 证据）", en: "the matrix (requirement × evidence)" },
    iron: {
      zh: "每条需求一个 contract_id，每行带 PASS/FAIL/UNVERIFIED 与 evidence_type。矩阵是「可验证的整体」；`EvidenceType` 在 `Matrix.tsx` 里有中文释义。",
      en: "Each requirement gets a contract_id; each row carries PASS/FAIL/UNVERIFIED and an evidence_type. The matrix is the verifiable whole; `EvidenceType` has plain-language meanings in Matrix.tsx.",
    },
    anchor: "apps/web/src/pages/Matrix.tsx · #/matrix",
  },
  {
    term: "policy",
    gloss: { zh: "审判庭政策表", en: "review-court policy table" },
    iron: {
      zh: "裁决不是 AI 思考出来的，是 `specproof_review_court` 政策表钉住的——6 段：perf / 中性词表 / base 金额保全 / 等级 / severity nuking。由 `test_review_court_policy.py` 与 `test_matrix_pure.py` 锁住。",
      en: "The verdict is not thought up by the AI; it is pinned by the `specproof_review_court` policy table — six sections including the neutral-word list and severity nuking. Locked by test_review_court_policy.py and test_matrix_pure.py.",
    },
    anchor: "agent/review_court/policy.py",
  },
  {
    term: "spec",
    gloss: { zh: "需求清单（对人说话）", en: "the requirement spec (speaking to humans)" },
    iron: {
      zh: "与 contracts 不是一个东西：spec 是自然语言对人类的回答；contracts 是对机器的回答。一个 spec ⇒ 多个 contracts。",
      en: "Not the same as contracts: the spec is the natural-language answer to the human; the contracts are the answer to the machine. One spec yields many contracts.",
    },
    anchor: "agent/nodes/compile_requirements.py",
  },
  {
    term: "wkapi.pro",
    gloss: { zh: "本产品的真实模型端点", en: "this product's real model endpoint" },
    iron: {
      zh: "你实验过的真实端点：`https://wkapi.pro/v1`，模型 `gpt-6-sol`，协议 chat_completions；密钥只在 `.local/llm.json`，从不入库。双车道 chat() / chat_stream() 都开 include_usage——缓存命中才有数可记。",
      en: "The real endpoint: `https://wkapi.pro/v1`, model `gpt-6-sol`, chat_completions; the key lives only in `.local/llm.json` (never committed). Both lanes — chat() and chat_stream() — send include_usage, so cache hits always have a number to record.",
    },
    anchor: "providers/openai_compatible.py",
  },
];
