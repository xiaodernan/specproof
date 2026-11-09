# SECURITY.md — 安全与信任模型

## 报告安全问题

请在此仓库的 GitHub Security Advisory（`Security → Advisories → Report a vulnerability`）提交私有报告。不要在 issue 或 PR 里公开细节，先走私有通道，再与维护者对齐是否需要 CVE。

- 我们不接受通过本仓公开通道的漏洞赏赐申请；合规上的披露在私有通道内处理。
- 报告包含：位置（文件+行或函数名）、影响、已知条件（是否需要一个已登录身份）、以及最小复现。

## 支持范围

- **本项目尚无签名发版（tagged releases）。`master` 是唯一被维护的分支**；不存在"受支持版本/EOL 时间线"——在完成首次 tag 之前，一切说法以 master 的 HEAD 为准。
- `specproof mcp serve`（MCP over stdio）是实验性面；默认只听 stdin，绝不开端口、不引入任何额外信任。

## 信任模型（读给 reviewer）

1. **不受信仓库是执行对象，不是运行时权限**：基本策略是 Docker 沙箱——非 root uid 1000、`--network none`、只读挂载、`--cap-drop ALL`、`--pids-limit 256`、`no-new-privileges`。
   例外：Python lane 只有在 `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1` **显式**解锁后才在宿主跑（有意的自担风险开关）；默认红。
2. **模型生成的代码不被信任**：LLM 生成的反例/修复只作为候选静态工件，进入同一沙箱与同样的 diff 流程；没有任何"LLM 说过的就是对的"的特殊路径。
3. **存储 ≠ 证据**：capsule 是摘要 + 有限制的 zip；签名用 Ed25519，私钥在操作员环境，绝不入库；SHA-256 只是被签名的 canonical digest。
4. **鉴权与审计**：RBAC 矩阵（admin / operator / viewer / auditor）服务端按 role 判定；所有证据出口（证书、胶囊下载）已走 `audit_logs`；`DATA_DICTIONARY §1.8` 的 `action` 是受控词表，双向对账（code ↔ doc ↔ gate `test_audit_action_parity.py`）。
5. **密钥与凭证**：
   - 本仓不含任何真实密钥；`.env`、`.local/llm.json` 已 git 忽略；`.env.example` 只放占位符并与默认值对齐。
   - 凭证缺失/错误 **fail-closed**：guard 只在 SPECPROOF_ENV=production 时强制校验；dev 的默认口令在 compose 里供本地，生产路径拒绝引导（见 `storage/config_guard.py`、`tests/unit/test_production_guard_reachability.py`）。
6. **网络出度默认为零**（沙箱断网），AI 调用只经由设计好的 provider 适配器；不会出现"模型说什么都能跑"的回路。

## 已知限制（如实）

- 本项目不构成法律/合规意见（SOC2/ISO27001 认证非本项目成果；审计报告输出的是"机器可验证的事实"，不是合规背书）。
- 本机 docker daemon 在 2026-11-09 曾经对 `docker run/create` 降级（`#1540 实记`），observability 看板的**服务级**开箱未复验，静态配置在仓。
- pilot 仓与真实 provider 侧的生产验证未做（等用户/客户的接近真实数据）。
- 无 KMS/HSM 密钥托管；签名私钥的生命周期由运维负责。
- 备份/PITR/保留策略未被产品化执行，需要部署侧做排期和签字。
- 前端 "live" 视图的节点流是真实 worker 事件流 + 3 个演示 job 的历史 seed；不要从 seed 数据外推产品承诺。
- Node 沙箱只支持 lockfile 且无 `node_modules` 的仓库离线安装；未播种的包 → `ENOTCACHED` → `NON_REPRODUCIBLE`，不算通过。

## 何时不保证安全（也就是说，绝不要在以下场景当生产红蓝环境使用）

- 让不受信仓库在宿主直接跑它的测试——红线。
- 在没有 sandbox/uid 限制的 root 环境里处理不受信代码——红线。
- 不回看的依赖供应链（vendored 依赖、锁文件过旧）下任何"验收通过"——cargo/npm/maven/go 依赖的完整性不因本项目而变。
- 在生产库里启用无人回收的 CI 审查者凭证。请保持 operator 身份对密钥的控制。

## 联系

安全问题请走上面的私有通道；其余（设计/产品/印刷错误）请走仓库 issue。报告中请注明 HEAD 的 commit sha。
