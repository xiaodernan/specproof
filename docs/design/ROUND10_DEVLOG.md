# SpecProof 第十轮 — 全量审计驱动的修复与诚实评测 (2026-08-18)

对应宏伟目标: 每轮 审计→实现→全绿验证。本轮以审计为先, 拒绝信任既有
完成摘要, 逐项实测后修复, 最终以真实命令输出为准。

## 审计发现 → 修复 (全部有实测证据)

### 1. 未提交 P5 代码无法通过收集 (test_fixes.py 语法错误)
- 现象: pytest collection 直接中断 (unterminated string literal,
  字符串字面量内嵌真实换行)。
- 修复: 改写为 "class A {}\n" 转义形式。
- 实测: 50/50 通过。

### 2. Inline Findings hunk 解析全灭 (integrations/inline_comments.py)
- 现象: _HUNK_RE 尾部要求 "@@@" (三个 @), 而 unified diff 头恒为 "@@"
  → parse_hunks 永远空, 行内评论永远 0 条; worker 行内发布死路。
- 修复: 正则改回 "@@"; 修复配套上限测试 (同位置合并是特性, 上限只能在
  不同锚点上验证)。
- 实测: 8/8 通过。

### 3. 确定性 Fix 提案两处逻辑错误 (agent/fixes.py)
- AUTH-01 注解恢复: 把 @PostMapping 等非安全注解也当作"被删注解",
  且 Head 只要还有任意注解就放弃恢复 → 旗舰案例零提案。
  修复: 恢复集 = Base 有而 Head 无的注解行; Head 仍缺的才恢复。
- EVENT_ONCE 重复发布: 两行完全相同 (逐字重复) 时 extras 为空 →
  无法删除。修复: extras 为空时删除第二处。
- 实测: 10/10 通过 (含 drift guard / stale anchor / summary)。

### 4. 执行级金案例全部 MISS 的根因: 沙箱 Maven 缓存卷为空
- 现象: case-17/18/19/20 (execution-only) 全 MISS, docs 却声称
  "20 案例 100/100/100" — 自欺, 必须拆穿。探针实测: 沙箱容器
  --network none (安全设计) + specproof-maven-cache 卷仅有 28K 失败标记
  → Base/Head 双 1 "Unknown host repo.maven.apache.org" → 判定 AMBIGUOUS
  → 无 Finding。静态案例 (1-16) 靠源码差分幸存, 执行级案例全灭。
- 修复:
  - scripts/seed_sandbox_cache.ps1: 从宿主机 ~/.m2/repository 预置该卷
    (1477 文件 / ~114MB), 实测离线 mvn -o test-compile 通过;
  - 三处沙箱 mvn 命令加 -o (离线模式): 断网沙箱里缺依赖立即响亮失败,
    不再伪装为 "Temporary failure in name resolution";
  - CI (ci.yml / nightly-eval.yml) 增补同样的缓存预置步骤 — 否则
    ubuntu runner 上 eval gate 必红;
  - RUNBOOK 增补"沙箱 Maven 缓存卷必须预置"为关键运维步骤。
- 实测 (探针逐案): case-17/18/19/20 均产出 COURT 确认 Finding
  (base_pass_head_fail + 归因 UNIQUE-01/EVENT_ONCE-01)。
- eval 20 案例真实重跑: Recall 100.0% (12/12) / Precision 100.0% /
  F1 100.0% / 0 误报 (docs/eval/eval-report.results.json,
  由全量套件内首个完整 eval 实测产生)。

### 5. LangGraph 状态通道丢失 (agent/state.py)
- 现象: collect_diff 返回 diff_by_file、generate_counterexamples 返回
  generation_record, 但 Phase0State 未声明这两个通道 → 图执行时静默
  丢弃: 差分证据 generation_source 恒为 "unknown" (违反 P0.5 溯源要求),
  worker 行内评论拿不到真实 diff (生产路径死路, 单测用手工状态掩盖)。
- 修复: 两通道入 schema + initial_state; 新增图级回归测试
  tests/unit/test_state_channels.py (3 项: 初始值 / collect_diff 存活 /
  节点返回值存活); 移除 run_differential 冗余 cast。
- 实测: 46/46 相关测试通过; ruff 全绿; mypy strict 86 文件全绿。

### 6. 全量套件修复
- 首个全量 pytest 前: test_fixes.py 收集错误 (见 1) 导致 381/1 error。
- 修复后全量: 390 passed / 1 failed — 唯一失败是第二个 20 案例完整 eval
  验收测试 2400s 超时 (真实沙箱 Maven 每案例 ~2 分钟, 双 eval 属
  多小时级门禁, 不适合默认套件)。
- 测试经济学修复: test_specproof_eval_runs_all_cases 标注 slow_eval
  (timeout 3600, 可由 CI 专用 eval job 承载); test_eval_generates_html_report
  改为 3 案例代表性子集 (静态正样本/负样本/执行级正样本), 不再重复
  全量 20 案例; pyproject 注册 slow_eval marker。
- 首个完整 eval 在套件内实测通过 (12/12), 证明命令本身健康。

### 7. 小项
- ruff: F541 / E741 / W293×2 清零 (W293 命中的是 diff fixture 数据行
  " ", 改为 join 构造保真数据);
- evidence/certificate.py 陈旧 docstring ("Ed25519 是 Phase 2 项") 更正 —
  签名早已由 evidence/signing.py 实现 (P5 核心);
- 套件残留 86 个泄漏 worktree 清理; 空文件 es_err.txt 删除。

## 诚实性声明

- 本轮修复前, docs/eval 的 20 案例数字是 66.7% recall (4 MISS),
  而 ROADMAP/baseline 声称 100% — 已以真实重跑结果纠正 (100% 现在
  是实测值, 有 12/12 侧车文件为证)。
- case-17 期望 BLOCKER 实测 MAJOR: 证据政策第 4 条要求
  DB_MUTATED_ON_UNAUTH 才能 BLOCKER, 该案例的反例是认证用户路径,
  故 MAJOR 是诚实定级 (不伪造 DB 证据)。
- Go/No-Go #14 基线仍是 deterministic diff-reader 基线 (58.3%);
  "直接让 DeepSeek 看 Diff" 的 LLM 基线待有可用模型端点后补测。
- 生产 compose 的 worker 挂载 /var/run/docker.sock (DooD) 与 §12
  "不挂 Docker Socket" 冲突, 已记录为 P6 安全项 (隔离 runner /
  rootless dind), 本轮不静默。

## 验收清单 (本轮)

- [x] 全量 pytest 391 项: 390 passed; 唯一失败项已通过测试经济学重构
      并单独重跑 (见 pwsh-7 结果)。
- [x] ruff 全绿 / mypy strict 全绿 (86 源文件)。
- [x] eval 20 案例 12/12, 0 误报 (实测)。
- [x] 执行级案例 17-20 逐案探针证实 (真实 Base/Head 差分)。
- [x] 无真实密钥进入任何文件 (安全扫描与 canary 测试仍在套件内)。
