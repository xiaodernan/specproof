# SpecProof 企业级加固开发记录 (2026-08-17, 第三轮)

对应 docs/design/ENTERPRISE_AUDIT.md 的 P0/P1 修复。

## 本轮修复的 P0 漏洞

1. **A1 实验执行沙箱** — sandbox/runner.py:
   Docker 容器执行 (--network none、--cap-drop ALL、no-new-privileges、
   --memory/--cpus、tmpfs /tmp、不挂 docker.sock、不传宿主 env),
   Maven 编译与差分测试全部经由沙箱; SPECPROOF_SANDBOX=auto|docker|local,
   auto 降级 local_fallback 并记录 sandbox_mode (证据诚实)。
   注: 本机 Docker Hub 不可达 (registry-1.docker.io 直连超时), 沙箱镜像
   maven:3.9-eclipse-temurin-21 未能拉取 → 实测走 local_fallback;
   生产环境配好 registry 即获得完整隔离。
2. **A2 API 鉴权与限流** — api/auth.py:
   X-API-Key 常数时间比较 (未配置密钥=503 fail-closed, 绝不开放),
   Redis 固定窗口限流 (默认 60 req/min, Redis 不可用=允许并记录),
   CORS 白名单 (SPECPROOF_CORS_ORIGINS, 默认仅 localhost)。
   测试: 401 无钥/错钥、503 未配置、429 路径、SSE 同样受保护。
3. **A3 模型传输脱敏** — providers/redaction.py:
   sk-/ghp_/PAT/AKIA/私钥块/Bearer/JDBC/URL 凭据/JWT 正则替换为
   [REDACTED:<kind>], compile_contracts LLM prompt 已接入; 7 个单测。
4. **B1 版本化迁移** — storage/migrations.py + infra/mysql/migrations/:
   schema_migrations 版本表 + 0001_init.sql + 0002_cancel_audit.sql,
   ensure_tables 委托迁移执行器。修复"注释行吞掉同段 ALTER"的
   拆分 bug (原 0002 的 enum ALTER 被静默丢弃 — 实测 SHOW COLUMNS 证实)。
5. **A5 审计表** — audit_logs 表 + transition_job_status 自动写审计行
   (actor/from/to/detail), 审计失败不影响主流程 (best-effort + 日志)。

## 本轮功能扩展

6. **B2/B3 状态机 10 态 + 任务取消** — 新增 CANCELLED 与
   WAITING_FOR_PROVIDER (可恢复的 Provider 故障态); 迁移 0002 扩展 enum;
   POST /jobs/{id}/cancel (CAS, 终态 409)。
7. **C4 CI 修复** — 原 eval gate grep 一个不存在的 eval-run.log (恒失败);
   改为 tee 真实输出 + Recall/FP 双门槛 + artifact 上传; 新增
   nightly-eval.yml (每日 02:00 UTC, 回归即红)。
8. **A4 配置生产校验** — (本轮未做, 列入下轮)

## 实测

- ruff 全绿 / mypy strict 通过 (66 源文件)
- 内核测试 48 passed (状态机 10 态/取消/迁移/注册表, 真实 MySQL)
- 迁移实测: 删除版本 2 记录后重放, enum 由 8 值正确扩展为 10 值
- 安全测试: 排除"模式定义/合成密钥"模块 (redaction/security_scanner) 后全绿
- 全套测试见最终 pytest 运行
