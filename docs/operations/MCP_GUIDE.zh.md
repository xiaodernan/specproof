# SpecProof MCP 指南 —— 把外部 AI Agent 接进验收流水线

> **English edition**: [MCP_GUIDE.md](./MCP_GUIDE.md) · 本文件是它的中文版，内容逐条对应。

SpecProof 自带一个 **stdio 上的 MCP 服务器**。这是最通用的机器对机器接线方式：任何 AI-agent 宿主
（Claude Code、Codex CLI、Cursor、OpenCode，或任何 stdio JSON-RPC 客户端）都可以直接调用
`specproof_verify`、读取契约、查询评测结果、检查 bug 复现包——走的是**与你手敲完全相同的验收流水线**。

本文件是运维者手册：怎么起服务、怎么接进你在用的 agent 宿主、这些工具会答什么不会答什么、
以及怎么端到端冒烟测一遍接线。

---

## 一、启动服务器

```bash
cd <specproof-repo-root>
specproof mcp serve
```

它会跑一个 JSON-RPC 2.0 的 stdio 循环，直到 stdin 关闭（EOF）。**没有别的传输方式**
（刻意不支持 HTTP/SSE——这个服务器本来就该跑在运维者的信任边界内）。

**工具目录**，不用起客户端就能打印：

```bash
specproof mcp tools           # 人读的
specproof mcp tools --json    # 与服务器 tools/list 回的是同一份载荷
```

**协议**：`initialize`、`tools/list`、`tools/call`、`ping`（外加通知类消息，静默消费）。
收到畸形消息时服务器**从不退出**；协议错误以 JSON-RPC 错误码返回。

---

## 二、服务器会告诉你什么（以及不会告诉你什么）

暴露的工具（`specproof mcp tools` 的输出永远是你手上这个 commit 的权威目录）：

| 工具 | 做什么 | 你可以信什么 |
|---|---|---|
| `specproof_verify` | 在子进程里跑 `specproof verify`，可能耗时数分钟 | 判决 + severity/confidence 信号 + 复现包名；以及 CLI 自己的 stdout |
| `specproof_verify_job` | 创建一个验收**作业**（outbox + worker 流水线） | 只有在作业行真的落库后才回 `QUEUED` |
| `specproof_contracts_list` | 列出契约登记表条目 | MySQL 不可达时返回降级载荷；**从不编造** |
| `specproof_eval_summary` | 读 `docs/eval/eval-report.results.json` 里最新的 precision/recall/F1 | 指标是持久化产物；缺失 = 明确报错，绝不虚构 |
| `specproof_craft_plan` | 确定性 `craft plan --no-llm` 的输出 | 工具内部**从不**调用远程 LLM |
| `specproof_health` | 探测 MySQL/MongoDB/ES/Redis/RabbitMQ/MinIO | 按依赖降级；报真实错误 |
| `specproof_replay_info` | 检查一个 bug 复现包 | 有路径穿越防护；绝对路径一律不接受 |

**你免费拿不到的承诺**：没有配置好流水线的工具调用，会带明确原因地降级回答。
**没有一句是悄悄编出来的**——这与 HTTP API 和 CLI 是同一套诚实合约。

---

## 三、接进客户端

### Claude Code（项目根目录的 `.mcp.json`，或 `claude mcp add`）

```json
{
  "mcpServers": {
    "specproof": {
      "command": "specproof",
      "args": ["mcp", "serve"],
      "env": {}
    }
  }
}
```

或在仓库根目录执行：

```bash
claude mcp add specproof -- specproof mcp serve
```

### Codex CLI（`.codex/config.toml` / `codex config set mcp.specproof …`）

```toml
[mcp.servers.specproof]
command = "specproof"
args = ["mcp", "serve"]
```

### Cursor（`~/.cursor/mcp.json`）

```json
{
  "mcpServers": {
    "specproof": {
      "command": "specproof",
      "args": ["mcp", "serve"]
    }
  }
}
```

### OpenCode（见 `opencode/opencode.json` / `config`）

```json
{
  "$schema": "https://opencode.sh/schema.json",
  "mcp": {
    "specproof": {
      "type": "local",
      "command": "specproof",
      "args": ["mcp", "serve"],
      "enabled": true
    }
  }
}
```

共同形状就是 `command = specproof`、`args = ["mcp", "serve"]`——服务器说 stdio JSON-RPC，
**不需要端口、不需要网络可达、不需要任何额外凭据**（除了 `specproof verify` 自己对目标仓库
本来就需要的东西）。

---

## 四、冒烟测接线

```bash
# 1. 服务器能答 tools/list
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | specproof mcp serve
#   => {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

# 2. 目录与 CLI 看到的一致
specproof mcp tools --json | python -c "import json,sys; nb={t['name'] for t in json.load(sys.stdin)}; print(len(nb),'tools'); print(sorted(nb))"

# 3. 端到端探一下流水线（需要一个仓库 + 需求文件）
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"specproof_health","arguments":{}}}' | specproof mcp serve
```

如果第 2 步回 `0 tools`，去看 `specproof mcp tools --json` 的输出形状——服务器永远回同一份数组。

---

## 五、排障

| 症状 | 大概率原因 | 处置 |
|---|---|---|
| 客户端调用成功但答案降级为 `cannot reach …` | worker 没起 / 依赖挂了 | 起 API + worker（见 `docs/operations/RUNBOOK.md`），查 `specproof mcp tools` + `specproof health` |
| stdio 输出乱码 / 工具结果里有 `\ufffd` | 宿主 locale 与 PYTHONIOENCODING 不一致 | 服务器两端都钉死了（`mcp/tools.py::_run_cli`）；若你自己管道传中文，前缀 `PYTHONIOENCODING=utf-8` |
| `method not found: tools/list` | 客户端把 `tools/list` 当通知发了（没有 `id`） | 通知被静默消费；带上 `id` 才有响应 |
| 长时间调用超时 | `specproof mcp serve` 里的 `specproof_verify` 对 CLI 子进程不可中断 | 外面套 `timeout`，或改用 `specproof_verify_job`（异步）+ 进度 SSE |
| `SpecProof tool error: unknown tool …` | 客户端在幻觉工具名 | 重跑 `specproof mcp tools` 拿权威目录 |

---

## 六、边界（依赖之前请读这一节）

- **只有 stdio。** 没有 TCP 传输。这是刻意的：SpecProof 不假装自己是一个网络可达的服务；
  任何与它对话的 agent，都跑在和 CLI 同一台机器上（或 `docker compose exec` 进去）。
- **安全模型就是子进程信任。** MCP 服务器继承启动它的那个 shell 的信任模型；
  在共享主机上跑 `specproof mcp serve`，等于把它交给了所有能读它 stdin 的 agent。
- **跑流水线的工具很慢**（`specproof_verify` 以分钟计）且无上界；调用方有超时就一定要套上。
- **没有增量 tools/list 通知。** 工具集在服务器进程生命周期内是静态的；构建变了就重启服务器。

---

## 七、参考

- 真相之源：`mcp/server.py`、`mcp/tools.py`
- CLI：`specproof mcp serve`、`specproof mcp tools [--json]`
- 测试：`tests/unit/test_mcp_server.py`、`tests/unit/test_mcp_client.py`、
  `tests/unit/test_mcp_tools_command.py`、`tests/unit/test_mcp_cli_output_codec.py`
- 本文件由 `docs/operations/EXPERIENCE_GUIDE.md` 第 7 步引用。
