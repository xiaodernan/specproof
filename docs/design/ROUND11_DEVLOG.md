# SpecProof 第十一轮 (P6) — 生产就绪推进 (2026-08-18)

对应宏伟目标: 每轮 审计→实现→全绿验证。本轮目标 (P6):
100 金案例、沙箱非 root、DooD 修复、Grafana/SLO 可观测栈、
17 份 ADR、LLM 基线、Go/No-Go 15 门槛测量文档。
(并行启动: SpecCraft 自主开发 Agent, 见 docs/design/SPECCRAFT_PLAN.md)

> 状态: 进行中 (队长持续追加实测结果)

## 审计发现 (Round-11 audit)

### A1. bandit Medium+ 复燃: cli/specproof/commands/fix.py 4× B113
- 现象: approve 命令把本地 JSON 字典命名为 requests, bandit 将其
  误判为 requests 库无超时调用 (B113 Medium ×4), 违反"Medium+ 归零"。
- 修复: 局部变量改名 fix_requests (消歧义而非 #nosec 压制)。
- 实测: bandit -ll 复测 0 Medium/High; ruff 全绿; test_fixes 10/10;
  unit/security/fault 315 passed。

## 并行实现 (子代理 B/C/E/A/F)

### E: 17 份 ADR + LLM 基线 + Go/No-Go (已完成)
- docs/adr/ADR-001..017.md 独立拆分 (7 份新撰写, 过期 ADR-009 被
  新 ADR-011 取代, LEGACY 合并文件保留), docs/adr/README.md 索引。
- baseline --mode {diff-reader,llm}: 复用 provider JSON Envelope 降级;
  无 Key/probe 失败 → "LLM baseline unavailable" exit 2, 绝不编数字。
- docs/eval/go-nogo.md: PASS 6/15 · PARTIAL 3/15 · PENDING 6/15,
  逐条证据/命令/缺口, 未测项如实 PENDING。
- 实测: ruff/mypy 全绿 (87 文件); test_baseline 31 passed;
  冒烟 diff-reader 复现 recall 58.3% / +41.7pp PASS。
- 诚实遗留: LLM 基线实测需真实 Key (补测步骤已写文档);
  responses 0.26.2 无 httpx 集成 → probe 失败测试改 transport stub。

### C: OTel/Prometheus/Grafana 可观测栈 (已完成, B104 修复中)
- compose.observability.yml + infra/otel + infra/prometheus (7 条 SLO
  告警, promtool 校验通过) + infra/grafana (15 面板 SLO 看板) +
  docs/operations/OBSERVABILITY.md。
- Python 侧: observability/metrics_http.py (worker:9100 / relay:9101),
  observability/metrics.py 直方图 (桶对齐 §14 p50/p95),
  agent/worker.py 完成时长记录, storage/outbox_relay.py 指标端口。
- 实测: prometheus/grafana 健康 200; 5 目标全 up (api down→up 翻转);
  Grafana→Prometheus→指标端到端查询打通; 测试后容器/端口/卷零残留。
- 整合待办: ① metrics_http B104 → 绑定地址环境变量化 + nosec (C 修复中);
  ② compose.production.yml 补 OTEL_EXPORTER_OTLP_ENDPOINT + outbox-relay
  服务 (已转 B); ③ 未接线指标清单已入 OBSERVABILITY.md §6。
- 镜像站记录: daocloud 拉取 retag (prom/prometheus v3.3.1, grafana
  11.6.1, otel-collector-contrib 0.123.0), compose 保持标准 tag。

### B: 沙箱非 root + DooD (已完成)
- sandbox/runner.py: --user 1000:1000 + --pids-limit 256 + workspace :ro
  (仅 target/ 可写子挂载, 实测源码写被拒) + MAVEN_USER_HOME=/home/maven/.m2
  + MAVEN_OPTS=-Duser.home=/home/maven (实测修正: MavenWrapperMain 把
  MAVEN_USER_HOME 当 .m2 本身; mvn 忽略该变量; 镜像无 maven 用户, uid1000=ubuntu)。
- DooD: worker 不再挂 /var/run/docker.sock, 改专用 docker:27-dind sandbox
  服务 (网络内 2375 明文 TCP; rootless dind 实测失败 — 命名卷 root 属主 +
  sub-uid 重映射问题, compose 注释 + RUNBOOK 记录取舍)。
- 全链路实测: dind 内离线 mvn 编译 exit 0; case-17 探针 PASS (UNIQUE-01,
  MAJOR 粒度与改造前一致); seed 脚本端到端 SEED_OK (uid-1000 卷)。
- 门禁: 13 新单测全绿; unit 300 passed; mypy 97 文件; 自身文件 bandit 0 Medium+。
- 队长整合: compose.production.yml 补 api/worker OTEL_EXPORTER_OTLP_ENDPOINT +
  新增 outbox-relay 服务 (C 发现的缺口); 三文件 compose config exit 0。

### A: 100 金案例 (阶段一进行中)
- (完成后由队长填入实测输出)

### F: SpecCraft M1 骨架 (进行中)
- (完成后由队长填入实测输出)

## 验证汇总

(完成后由队长填入: ruff/mypy/bandit/pytest/eval/compose 实测)