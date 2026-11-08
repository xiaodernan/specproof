# SpecProof MCP Guide — wire an external agent into verification

SpecProof ships an **MCP server** on stdio. That is the universal machine-to-
machine wiring that lets an AI-agent host (Claude Code, Codex CLI, Cursor,
OpenCode, any stdio JSON-RPC client) call `specproof_verify`, read contracts,
query evaluation results, or inspect a bug capsule — straight into the same
verification pipeline you would run by hand.

This file is the operator guide: how to start the server, how to wire it to
the agent hosts you use, what the tools will and will not answer, and how to
smoke-test the wiring end-to-end.

---

## 1. Start the server

```bash
cd <specproof-repo-root>
specproof mcp serve
```

Runs a JSON-RPC 2.0 stdio loop until stdin closes (EOF). There is no other
transport (HTTP/SSE is deliberately not supported — the server is intended
to run inside the operator's trust boundary).

**Catalog**, printable without starting a client:

```bash
specproof mcp tools           # human-readable
specproof mcp tools --json    # same payload the server answers `tools/list` with
```

**Protocol**: `initialize`, `tools/list`, `tools/call`, `ping` (plus
notifications, silently consumed). The server never exits on a malformed
message; protocol errors return JSON-RPC error codes.

---

## 2. What the server will tell you (and what it won't)

Tools exposed (`specproof mcp tools` output is always the authoritative
catalog for the exact commit you have):

| Tool | What it does | What you can trust |
|---|---|---|
| `specproof_verify` | Runs `specproof verify` in a subprocess. Can take minutes. | Verdict + severity/confidence signals + capsule names; the CLI's own stdout |
| `specproof_verify_job` | Creates a verification **job** (outbox + worker pipeline). | `QUEUED` only when the job row was actually persisted |
| `specproof_contracts_list` | Lists contract registry entries. | Degraded payload when MySQL unreachable; never fabricated |
| `specproof_eval_summary` | Latest `docs/eval/eval-report.results.json` precision/recall/F1. | Metrics are persisted artifacts; absent = explicit error, never invented |
| `specproof_craft_plan` | Deterministic `craft plan --no-llm` output. | Never calls a remote LLM from inside the tool |
| `specproof_health` | Probes MySQL/MongoDB/ES/Redis/RabbitMQ/MinIO. | Degraded per dependency; reports real errors |
| `specproof_replay_info` | Inspects one bug capsule. | Path traversal defenses; absolute paths never accepted |

**Never-claims you get for free**: a tool call without a configured pipeline
answers degraded with an explicit reason. Nothing is silently fabricated —
this is the same honesty contract as the HTTP API and the CLI.

---

## 3. Wire it into a client

### Claude Code (`.mcp.json` in project root, or `claude mcp add`)

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

or, from the repo root:

```bash
claude mcp add specproof -- specproof mcp serve
```

### Codex CLI (`.codex/config.json` / `codex config set mcp.specproof …`)

```toml
[mcp.servers.specproof]
command = "specproof"
args = ["mcp", "serve"]
```

### Cursor (`~/.cursor/mcp.json`)

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

### OpenCode (see `opencode/opencode.json` / `config`)

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

The common shape is `command = specproof`, `args = ["mcp", "serve"]` — the
server speaks stdio JSON-RPC and needs no port, network reachability, or
credential beyond what `specproof verify` itself expects for its target repo.

---

## 4. Smoke-test the wiring

```bash
# 1. The server answers tools/list
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | specproof mcp serve
#   => {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

# 2. The catalog matches the CLI's view
specproof mcp tools --json | python -c "import json,sys; nb={t['name'] for t in json.load(sys.stdin)}; print(len(nb),'tools'); print(sorted(nb))"

# 3. Inspect the pipeline end-to-end (requires a repo + spec)
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"specproof_health","arguments":{}}}' | specproof mcp serve
```

If step 2 returns `0 tools`, check `specproof mcp tools --json` output shape —
the server always answers with the same array.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Client calls work but answer degraded with `cannot reach …` | Worker not running / deps down | Start API + worker (§ docs/operations/RUNBOOK.md), check `specproof mcp tools` + `specproof health` |
| Stdio garbage / `\ufffd` characters in tool output | Host locale vs PYTHONIOENCODING | The server pins both ends (`mcp/tools.py::_run_cli`); if you pipe CJK yourself, prefix with `PYTHONIOENCODING=utf-8` |
| `method not found: tools/list` | Client sent `tools/list` as notification (no `id`) | Notifications are silently consumed; send `id` to get a response |
| Long-running call times out | `specproof_verify` inside `specproof mcp serve` is uninterruptible for the CLI subprocess | Spawn with `timeout`, or use `specproof_verify_job` (async) + progress SSE |
| `SpecProof tool error: unknown tool …` | Client hallucinating a name | Re-run `specproof mcp tools` to get the authoritative catalog |

---

## 6. Limits (read this before you depend on it)

- **stdio only.** No TCP transport. This is intentional: SpecProof does not
  pretend to be a network-reachable service; any agent that talks to it runs
  on the same host (or a `docker compose exec`) as the CLI.
- **Security is subprocess trust.** The MCP server inherits the trust model
  of the shell that launched it. `specproof mcp serve` on a shared host talks
  to every agent that can read its stdin.
- **Tools that run the pipeline are slow** (`specproof_verify` minutes) and
  unbounded; wire an external timeout when the calling agent has one.
- **No incremental tools/list notification.** The tool set is static per
  server process; restart the server to pick up a changed build.

---

## 7. Reference

- Source of truth: `mcp/server.py`, `mcp/tools.py`
- CLI: `specproof mcp serve`, `specproof mcp tools [--json]`
- Tests: `tests/unit/test_mcp_server.py`, `tests/unit/test_mcp_client.py`,
  `tests/unit/test_mcp_tools_command.py`, `tests/unit/test_mcp_cli_output_codec.py`
- Operator doc referenced from `docs/operations/EXPERIENCE_GUIDE.md`.
