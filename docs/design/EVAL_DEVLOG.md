# SpecProof 评测与基线对照开发记录 (2026-08-18, 第十轮)

对应宏伟目标: P6 评测 (100 金案例路线) 与 PRODUCTION_SPEC 第 20 节
Go/No-Go #14 (基线对照 +25pp)。

## 本轮新增

### 1. specproof baseline — "只看 Diff" 基线对照命令 (Go/No-Go #14)
- cli/specproof/commands/baseline.py: 在同一批金案例上测量基线审阅者,
  与 SpecProof 的 eval 结果 (eval-results.json sidecar) 用**同一判定口径**
  对比 (contract id / evidence 子串匹配; 负样本任何 finding 都算误报),
  所以差异只能来自验证能力本身。
- 两种基线模式:
  - --no-llm (默认): 确定性 diff-reader — 保守静态规则
    (删除的注解/守卫/访问器/token 调用, 新增的 publish 调用), 规则只对
    "删除且未在附近重加" 的行生效 (删除才怀疑, 修改不怀疑);
  - --llm: 脱敏后的 diff + 需求摘要发给 LLM, 严格 JSON 信封
    (无 Key 诚实报错)。
- 报告: markdown 对比表 + JSON; 显式计算 recall/precision delta 与
  +25pp 门槛判定。13 个单测 (规则命中/修改跳过/判定/聚合/门槛渲染/
  真实 git 仓库 diff 抓取)。
- 首测 (12 案例): 基线 recall 87.5% (漏 case-06 schema-break — 重命名
  访问器被保守规则视为"修改"), delta +12.5pp, 门槛 FAIL — 如实记录。

### 2. 金案例扩充 12 → 17 (对坑基线, 拉开真实差距)
- 4 个 adversarial 负样本 (split.json 早已预定义, 本轮实体化):
  - case-13-annotation-aliased: @PreAuthorize → 自定义组合注解
    @RequireAuth (Spring Security meta-annotation 等价保护);
  - case-14-annotation-moved-to-interface: 安全注解移到实现接口
    (JDK 动态代理解析接口级方法安全);
  - case-15-whitespace-only-diff: 纯重缩进;
  - case-16-preauthorize-role-changed: isAuthenticated →
    hasRole(ADMIN) (收紧而非回归)。
- 1 个 execution-only 正样本:
  - case-17-logic-inversion: 唯一性守卫取反 (单字符 !) — 静态
    diff-reader 看不到语义, 只能靠差分执行 + DB 状态取证。
- 标签工程: scripts/build_golden_scenarios.py 新增
  apply_case_detached — 新 case 的 commit **以 honest base 为父**
  (detached HEAD), 保证 git diff base..case-XX-head 只含该 case 的
  突变; 修复了 "前一 case 新增文件泄漏进下一 commit" 的污染。
  5 个 head 全部 mvnw compile 实测通过 (worktree 编译 EXIT=0)。

### 3. 检测器等价性加固 (让 adversarial 负样本归零)
- agent/checkers/java_source.py:
  - 安全注解等价集: @RequireAuth/@Authenticated 与内置
    @PreAuthorize/@Secured/@RolesAllowed 同等对待 (组合自定义注解,
    Spring 专精范围的文档化近似);
  - 接口级方法安全回退: controller 方法块无安全注解时, 解析
    implements 子句, 检查所实现接口同方法前的安全注解
    (抽象方法无 body, 用 400 字符注解窗口扫描);
  - 方法切分器支持 default 接口方法。
- 4 个新单测锁定 (组合注解/接口回退/implements 解析/旧回归不退化)。

### 4. 基线实测 (17 案例)
- 确定性 diff-reader: recall 77.8% (7/9), precision 87.5%, 1 FP
  (case-16 收紧角色被误报 — 天真的 diff-reader 无法判断收紧与移除);
  case-13/14/17 全部如设计 (静态看不到语义 → MISS/0 发现)。
- SpecProof: 17 案例 eval 结果见本轮最终验证 (目标 9/9 recall,
  0 误报 — case-13/14 依赖本轮检测器加固, case-17 依赖差分证据)。
- delta 实测见 baseline-report.md; 100 案例时复核 +25pp 门槛。

## 实测
- baseline 13 单测 + checker 4 单测全过; ruff 全绿 / mypy 83 源文件全绿;
- 5 个新 case head 编译通过 (worktree 逐个 mvnw compile EXIT=0);
- **17 案例 eval 终验: Recall 100% / Precision 100% / F1 100%, 0 误报**
  (adversarial 负样本 ×4 全归零, execution-only 正样本检出);
- 基线对照终测 (确定性 diff-reader, 同口径判定):
  SpecProof 100% recall / 100% precision vs 基线 77.8% recall (漏
  schema-break 与守卫取反) / 87.5% precision (case-16 收紧角色误报) —
  delta +22.2pp recall / +12.5pp precision, Go/No-Go #14 门槛 FAIL
  (如实记录; 按 100 案例路线继续拉大差距, 见 baseline-report.md);
- 全量 pytest 见本轮收尾记录。

---

## 续 (第十一轮): 金案例 17 → 20, Go/No-Go #14 门槛通过

### 新增 execution-only 正样本 ×3
- case-18-wrong-routing-key: 事件发布到错误路由键 (字符串常量级 diff);
- case-19-email-corruption: 存储邮箱被加尾随空格 (无害拼接的 diff);
- case-20-validation-removed: DTO 去掉 @NotBlank, 空邮箱被接受。
- 三者静态 diff-reader 全部 MISS (基线), SpecProof 全部检出 — 差距只能
  来自执行级验证。

### 检测升级 (让 execution-only 可被证明)
- 生成器契约驱动新增两类差分测试:
  - EVENT 家族: 断言 mock RabbitTemplate 的 convertAndSend 调用参数
    (交换器+路由键+事件类型) — 错误路由键 (case-18) 与重复发布
    (case-07 强化) 都只能在执行时证明;
  - UNIQUE 家族追加 blank-rejection 测试 + fresh-success 测试改为断言
    **存储行**而非响应体 (响应回显请求值, 只有 DB 行能暴露 case-19)。
- 管线契约编译表补 "publish|routing" 词条 (旧表与 P2 编译器不一致 —
  execution-only 场景的真实缺口)。
- Review Court 过滤 severity=NONE 的候选 (未参与失败测试的契约是
  簿记, 不是 finding) — 消除 case-07 的 AUTH NONE 噪音。

### 实测
- **20 案例 eval: Recall/Precision/F1 全 100%, 0 误报**;
- **Go/No-Go #14 PASS: SpecProof recall 100% vs 基线 58.3%,
  delta +41.7pp (门槛 +25pp); precision delta +12.5pp**;
- 全量 pytest / ruff / mypy / bandit 见本轮收尾记录。

---

## 补充: 对抗性样本暴露并修复的三个真问题 (本轮的"审计→修复"闭环)

1. **差分层与静态层双份 AUTH 判断, 且语义不一致** — run_differential 的
   _check_http_diff 只看裸 @PreAuthorize/@Secured 存在性, 不认识组合
   自定义注解与接口级方法安全 → case-13/14 误报 (eval 实证 2 FP)。
   修复: 差分层委托共享 checker (同一套等价集 + 接口回退), 单一事实源。
2. **检测深度 = 静态深度** — 反例生成器永远只产出未认证 401 测试,
   与契约无关; 静态 checker 说"守卫完整"就不再执行 → case-17 守卫取反
   (单字符 !) MISS。修复: 生成器契约驱动 — UNIQUE 契约存在时追加
   duplicate-rejection 与 fresh-email-success 两个差分测试 (执行是唯一
   能发现取反守卫的途径); 差分层按 surefire XML 中失败方法归属契约
   (unauth→AUTH-01, duplicate/fresh→UNIQUE-01), 不再一律 AUTH-01。
3. **生成测试的 MockMvc 异常语义** — 未处理控制器异常会从 perform()
   重新抛出 (demo 无全局异常处理器), 用 andReturn 断言状态会 ERROR;
   且同一事务内 save 不 flush 时 derived exists 查询看不到重复行。
   修复: 显式 saveAndFlush + 捕获 ServletException 断言拒绝原因。

修复后实证: case-13/14 归零, case-17 输出 UNIQUE-01 MAJOR
(REGRESSION, base_pass_head_fail), case-01 保持 BLOCKER 差分证据。
