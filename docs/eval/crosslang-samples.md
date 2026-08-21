# crosslang-samples — 跨语言案例样本 TS/Go (backlog #6)

状态: ✅ 样本交付 (离线、格式就绪); ⏳ 管线执行 unsupported (诚实标注)。

- 位置: `golden-cases-crosslang/` (2 案例) + 本说明。
- 允许清单: 仅新增 `golden-cases-crosslang/**` 与 `docs/eval/crosslang-samples.md`,
  未触碰任何既有文件, 未执行任何 git 命令, 未写入任何 API key。

## 样本清单与内容

| case | 语言 | 缺陷 | 三件套 |
|---|---|---|---|
| case-ts-01-auth-check-removed | TypeScript (node --test, 零依赖) | changeEmail 鉴权检查被移除 (镜像 case-01) | spec.md + ground-truth.json + scenario.json + src/{base,head} |
| case-go-01-validation-inverted | Go (go test) | EmailAllowed 黑名单判定单字符 ! 反转 (镜像 case-17) | spec.md + ground-truth.json + scenario.json + src/{base,head} |

scenario.json 沿用 golden-cases/ 的 schema (version 2.0, base_ref/head_ref),
但 refs 未在任何仓库物化 — 样本以 src/base + src/head 目录携带两个修订;
scripts/build_golden_scenarios.py 目前只构建 Java demo 案例。

## 真实可跑性 (2026-08-20, 全部为真实运行记录)

跑了什么:

1. 管线适配器检测 (真实 fail-closed): `registry.get(RepositorySnapshot)`
   对全部 4 个样本目录均抛 AdapterNotImplemented — Node/Go 为 planned 行,
   无执行器 → TS/Go 差分执行与测试生成**当前不支持**。
2. TS 直接工具链 (node v24.17.0): base `node --test` **2 pass exit 0**;
   head **1 pass / 1 fail exit 1** (真实断言: actual
   'EMAIL_CHANGED:attacker@evil.com' vs expected 'UNAUTHORIZED') —
   缺陷场景语义真实成立。
3. TS 类型检查: 仓库 vendored tsc `--noEmit` 首跑 TS2307 (样本不捆
   @types/node) → 加离线类型垫片 src/types.d.ts 后 base/head 均 exit 0。
4. 门禁: `python -m pytest tests/ -k "adapter or polyglot" -q`
   **60 passed in 6.84s** ✅ (首跑被 craft/loop.py:2371 的瞬时
   IndentationError 中断 — 该文件 mtime 22:04:22 位于两次运行之间,
   系并发车道改写所致, 与本交付无关; 重跑干净)。补充:
   tests/integration/test_phase_acceptance.py 两例不变式 2 passed,
   golden-cases/ 100 案例不受影响。

没跑什么:

- Go: 本机 PATH 无 Go 工具链 → go test 未执行, 源码未经验证 (README 如实标注)。
- SpecProof 管线对 TS/Go 的差分执行/测试生成: 未支持, 未运行, **不伪造任何检出结果**。
- 不带 --repo . 跑 `specproof eval` 于本目录 (refs 未物化, 会误跑 Java demo)。

## 诚实边界

- 直接 node/tsc 运行只证明「缺陷场景语义」, 不是管线检出; 检出结果在
  Node/Go 适配器落地前不存在。
- should_detect=true 表达「若执行被支持时的期望检出」; 每例 ground-truth.json
  均带 `pipeline_execution_status: "unsupported"` 字段。
- 样本零依赖、零网络、零密钥, 全部可离线复跑 (复跑命令见目录 README)。

## 落地为「已支持」所需 (不在本交付范围)

1. experiments/adapters.py: 实现 NodeAdapter (npm/Jest 或 node --test) 与
   GoAdapter (go build/go test), 替换 detect_node/detect_go 的
   AdapterNotImplemented 路径 (兼容矩阵同改);
2. 案例物化: 扩展 scripts/build_golden_scenarios.py 或等价的跨语言 repo
   场景构建, 使 scenario.json 的 base/head 真实存在;
3. 实测后再把 matrix 状态从 planned 改为已支持, 并在此文档回填真实检出结果。
