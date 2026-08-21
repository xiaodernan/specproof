# 生产试点运行手册 (Go/No-Go #12/#13)

> 状态: 机制与手册就绪 · 测量保持 PENDING — 本手册让试点可执行, 但任何
> PASS 声明都要求真实试点数据回填, 不允许用手册内容替代测量。

## 1. 对应门槛

- **#12** 3 个真实仓库连续试点 2 周 (PENDING)
- **#13** 用户对高等级 Finding 接受率 ≥ 70% (PENDING, 依赖 #12 先启动)

两门槛的 PASS 只可能来自仓库外的真实运行; 仓库内可交付的是选择标准、安装
步骤、日志要求与统计口径。

## 2. 试点仓库选择标准 (3 个)

1. Spring Boot 3.x + Java 21 + Maven (与执行适配器兼容矩阵一致);
2. 技术栈包含 MySQL/Redis/RabbitMQ 中至少两项 (差分执行与状态取证的主场);
3. 团队规模 1-20 人, 使用 Claude Code/Codex/Cursor 等 Coding Agent 产出 PR
   (产品定位的细分市场);
4. 有持续 2 周以上的真实 PR 流 (试点期内每个仓库 ≥ 10 个 AI 生成 PR);
5. 仓库所有者同意安装 GitHub App 并允许 Check Run 评论。

排除: 重依赖单仓 (构建 > 8 分钟)、无测试文化、拒绝 App 安装的仓库。

## 3. GitHub App 安装清单

1. GitHub → Settings → Developer settings → GitHub Apps → New;
2. 权限: Pull requests 读, Checks 写, Issues 读 (inline findings),
   Contents 只读 (Base/Head 检出);
3. Webhook: 订阅 pull_request (opened/synchronize), 配置 webhook secret;
4. 环境变量注入 (仅环境, 绝不落盘): GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY /
   GITHUB_WEBHOOK_SECRET;
5. 验证: POST /webhooks/github 验签 (HMAC 恒定时间比较) + delivery 去重
   (tests/unit/test_github_webhook.py 已覆盖 fail-closed)。

## 4. 两周运行日志要求 (每 Job 必录)

- Job 发起方式 (CLI/Web/MCP/GitHub) 与租户;
- 终态 (VERIFIED/BLOCKED/FAILED) 与耗时 (p95 目标 ≤ 8 分钟, FAST 口径);
- Finding 清单: contract_id / severity / evidence_type / 证据摘要;
- Capsule 下载与重放结果 (重放成功率口径同 #4);
- 故障记录: provider 故障/沙箱失败/超时 — 与 Drill 2 同口径。

## 5. #13 反馈协议 (accept/reject 统计)

- 对象: 试点仓库用户对每一个 BLOCKER/MAJOR Finding 做 accept/reject 决策;
- 判定: accept = 用户认可该 Finding 真实并据此修改了 PR; reject = 用户认为
  误报或不值得处理 (需附一句理由, 理由入审计);
- 统计: acceptance_rate = accepted / (accepted + rejected), 目标 ≥ 70%;
- 无反馈的 Finding 不计入分母 (不把沉默当 accept — 防自欺)。

## 6. 试点收尾与门槛回填

两周结束后按 go-nogo.md 的测量命令回填 #12/#13 证据引用:

- #12: 3 仓库 × 2 周的 Job/Webhook/Check Run 日志目录 + 逐仓库统计;
- #13: 逐 Finding 反馈清单 + acceptance_rate 计算;
- 生产口径的 #1/#2/#3/#4/#6/#7/#8/#9/#11/#14 也随试点数据复核 (各门槛
  的「生产 PR 流量口径」备注)。

任一门槛未回填真实数据前, 不宣称商业优势 9.0 成立。
