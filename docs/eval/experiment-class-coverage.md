# 实验类样本覆盖 (experiment class sample coverage)

由 `scripts/write_experiment_class_coverage.py` 生成；
`tests/unit/test_experiment_class_samples.py` 校验它与
`experiments/experiment_classes.py` 注册表一致——
**记录下来的缺口不会悄悄变成覆盖率声明**。

每个实验类需要三个样本：

- **正样本**（positive）：必须被抓到的缺陷；
- **负样本**（negative）：不得被误报的重构/注释改动；
- **holdout**：留出给评测的案例（调参时不看）。

holdout 缺失是真的缺口，不是格式问题：一个案例不能既是调参样本又是 holdout。

| 实验类 | 契约家族 | 机制 | 正样本 | 负样本 | holdout |
|---|---|---|---|---|---|
| transaction_rollback | ATOMICITY-01 | 生成式差分测试 | ✅ case-31-tx-decrement-committed-before-validation | ✅ case-34-tx-equivalent-dedup-lookup | ✅ case-39-tx-cancel-no-restock |
| concurrency | CONCURRENCY-01 | 生成式差分测试 | ✅ case-29-tx-optimistic-lock-removed | ✅ case-30-tx-version-guard-moved-to-getter | — |
| unique_constraint | UNIQUE-01 | 生成式差分测试 | ✅ case-19-email-corruption | ✅ case-78-logic-email-input-trimmed | ✅ case-04-duplicate-email |
| idempotency | IDEMPOTENT-01 | 生成式差分测试 | ✅ case-33-tx-order-idempotency-dedup-removed | ✅ case-36-tx-new-order-lookup-endpoint | ✅ case-35-tx-stock-decrement-off-by-one |
| cache_consistency | CACHE-01 | 生成式差分测试 | ✅ case-57-redis-cache-ttl-removed | ✅ case-59-redis-cache-helpers-extracted | ✅ case-58-redis-cache-writeback-removed |
| openapi_schema_diff | BACKWARD_COMPATIBLE-01 | 静态检查器 | ✅ case-53-api-order-count-field-removed | ✅ case-52-api-new-product-detail-endpoint | ✅ case-06-schema-break |

## 缺口

- **concurrency**（CONCURRENCY-01）缺：holdout

补一个案例需要走 `scripts/build_golden_scenarios.py` 的数据定义（`_case(...)` 一条），并在 `docs/eval/holdout-manifest.json` 登记（注意：该清单的 `family` 字段有新旧两套词表并存，见其 `note`）。
