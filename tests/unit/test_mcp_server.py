"""MCP stdio server tests: protocol matrix + per-tool honest degradation.

Covers the full message matrix from AGENT_STATE_OF_ART.md §9:
initialize / tools/list (>= 6 tools) / tools/call per tool (with mocked
subprocess + storage readers) / unknown tool / bad arguments / honest
degraded paths (MySQL down, missing eval report, missing capsule, CLI
non-zero exit, timeout, path traversal). Plus a real-subprocess stdio
smoke: the CLI is fed JSON-RPC over stdin and answers over stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

import mcp.tools as mcp_tools
from mcp.server import PROTOCOL_VERSION, SERVER_NAME, SpecProofMCPServer

PROJECT_ROOT = Path(__file__).resolve().parents[2]

VERIFY_STDOUT = """Job ID: 11111111-2222-3333-4444-555555555555
Repository: C:\\repo\\demo
Base: base  ->  Head: head-v1
Spec: C:\\tmp\\spec.txt
Depth: FAST

Running verification pipeline...

Contracts compiled: 3
  [+] AUTH-01 (endpoint_checker) -> PASS
  [!] TRANSACTION-01 (transactional_checker) -> FAIL

Findings: 2 total (1 BLOCKER, 1 MAJOR, 0 MINOR)
  [BLOCKER] AUTH-01 (confidence: 95%, evidence: differential_test)
       Endpoint changeEmailWithoutAuth is no longer protected.
  [MAJOR] TRANSACTION-01 (confidence: 82%, evidence: static_regex_analysis)
       @Transactional removed from saveAll path.

Matrix: 3 rows | +1 passed | -2 failed | ?0 unverified
Bug Capsules: 2 generated
  C:\\tmp\\reports\\capsules\\capsule-AUTH-01.zip
  C:\\tmp\\reports\\capsules\\capsule-TRANSACTION-01.zip

VERDICT: BLOCKED

HTML Report: C:\\tmp\\reports\\report.html
Rejection Notice written -> C:\\tmp\\reports\\rejection-notice-11111111.json
"""


# ── Helpers ─────────────────────────────────────────────────────────────────


def _rpc(method: str, params: Any = None, msg_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}


def _exchange(server: SpecProofMCPServer, message: Any) -> dict[str, Any]:
    raw = server.process_line(json.dumps(message))
    assert raw is not None, "expected a response"
    return json.loads(raw)


def _call_result(
    server: SpecProofMCPServer, name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = _exchange(
        server,
        _rpc("tools/call", {"name": name, "arguments": arguments or {}}, 7),
    )
    assert "error" not in response, response
    return response["result"]


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    assert result.get("isError") is False, result
    assert result["content"][0]["type"] == "text"
    return json.loads(result["content"][0]["text"])


def _error_text(result: dict[str, Any]) -> str:
    assert result.get("isError") is True, result
    assert result["content"][0]["type"] == "text"
    return result["content"][0]["text"]


@pytest.fixture()
def server() -> SpecProofMCPServer:
    return SpecProofMCPServer()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


# ── Protocol matrix ─────────────────────────────────────────────────────────


def test_initialize_declares_protocol_and_server_info(server: SpecProofMCPServer) -> None:
    response = _exchange(server, _rpc("initialize", {"protocolVersion": "2024-11-05"}))
    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSION == "2024-11-05"
    assert result["serverInfo"]["name"] == SERVER_NAME == "specproof"
    assert result["serverInfo"]["version"]
    assert result["capabilities"]["tools"]["listChanged"] is False


def test_tools_list_returns_all_seven_tools(server: SpecProofMCPServer) -> None:
    result = _exchange(server, _rpc("tools/list", {}, 2))["result"]
    names = sorted(tool["name"] for tool in result["tools"])
    assert names == [
        "specproof_contracts_list",
        "specproof_craft_plan",
        "specproof_eval_summary",
        "specproof_health",
        "specproof_replay_info",
        "specproof_verify",
        "specproof_verify_job",
    ]
    assert len(result["tools"]) >= 7
    for tool in result["tools"]:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"]


def test_ping_returns_empty_result(server: SpecProofMCPServer) -> None:
    result = _exchange(server, _rpc("ping", {}, 3))["result"]
    assert result == {}


def test_notification_gets_no_response(server: SpecProofMCPServer) -> None:
    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert server.process_line(json.dumps(message)) is None


def test_unknown_method_returns_jsonrpc_error(server: SpecProofMCPServer) -> None:
    response = _exchange(server, _rpc("resources/list", {}, 4))
    assert response["error"]["code"] == -32601
    assert "resources/list" in response["error"]["message"]


def test_parse_error_returns_jsonrpc_error(server: SpecProofMCPServer) -> None:
    raw = server.process_line("{not json")
    assert raw is not None
    response = json.loads(raw)
    assert response["error"]["code"] == -32700


def test_batch_of_messages_is_answered(server: SpecProofMCPServer) -> None:
    raw = server.process_line(
        json.dumps([_rpc("ping", {}, 1), _rpc("tools/list", {}, 2)])
    )
    assert raw is not None
    responses = json.loads(raw)
    assert isinstance(responses, list)
    assert [r["id"] for r in responses] == [1, 2]


def test_unknown_tool_returns_iserror(server: SpecProofMCPServer) -> None:
    result = _call_result(server, "specproof_nope", {})
    assert "unknown tool" in _error_text(result)


def test_non_object_arguments_rejected(server: SpecProofMCPServer) -> None:
    response = _exchange(
        server, _rpc("tools/call", {"name": "specproof_health", "arguments": [1]}, 8)
    )
    assert "arguments" in _error_text(response["result"])


def test_missing_required_argument_returns_iserror(server: SpecProofMCPServer) -> None:
    result = _call_result(server, "specproof_verify", {"repo": "somewhere"})
    assert "missing required argument" in _error_text(result)


# ── specproof_verify ────────────────────────────────────────────────────────


def test_verify_parses_verdict_findings_and_capsules(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)

    def fake_run_cli(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        assert cmd[:6] == [
            sys.executable, "-m", "cli.specproof.main", "verify", "--repo", str(repo),
        ]
        return subprocess.CompletedProcess(cmd, 0, stdout=VERIFY_STDOUT, stderr="")

    monkeypatch.setattr(mcp_tools, "_run_cli", fake_run_cli)
    result = _call_result(
        server,
        "specproof_verify",
        {"repo": str(repo), "base_ref": "base", "head_ref": "head-v1", "spec_text": "REQ: auth"},
    )
    payload = _payload(result)
    assert payload["verdict"] == "BLOCKED"
    assert payload["job_id"] == "11111111-2222-3333-4444-555555555555"
    assert payload["contracts_compiled"] == 3
    assert payload["findings_summary"] == {"total": 2, "blocker": 1, "major": 1, "minor": 0}
    assert payload["findings"] == [
        {
            "severity": "BLOCKER",
            "contract_id": "AUTH-01",
            "confidence": 0.95,
            "evidence_type": "differential_test",
            "description": "Endpoint changeEmailWithoutAuth is no longer protected.",
        },
        {
            "severity": "MAJOR",
            "contract_id": "TRANSACTION-01",
            "confidence": 0.82,
            "evidence_type": "static_regex_analysis",
            "description": "@Transactional removed from saveAll path.",
        },
    ]
    assert payload["matrix"] == {"rows": 3, "passed": 1, "failed": 2, "unverified": 0}
    assert payload["capsules"] == ["capsule-AUTH-01.zip", "capsule-TRANSACTION-01.zip"]
    assert payload["html_report"].endswith("report.html")
    assert payload["certificate"].endswith("rejection-notice-11111111.json")


def test_verify_rejects_missing_repo(server: SpecProofMCPServer, tmp_path: Path) -> None:
    result = _call_result(
        server,
        "specproof_verify",
        {"repo": str(tmp_path / "nope"), "base_ref": "b", "head_ref": "h", "spec_text": "x"},
    )
    assert "repository path does not exist" in _error_text(result)


def test_verify_nonzero_exit_returns_iserror(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(
        mcp_tools,
        "_run_cli",
        lambda cmd, timeout: subprocess.CompletedProcess(cmd, 2, stdout="", stderr="bad ref"),
    )
    result = _call_result(
        server,
        "specproof_verify",
        {"repo": str(repo), "base_ref": "base", "head_ref": "head", "spec_text": "x"},
    )
    assert "exited with code 2" in _error_text(result)
    assert "bad ref" in _error_text(result)


def test_verify_unparseable_output_returns_iserror(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(
        mcp_tools,
        "_run_cli",
        lambda cmd, timeout: subprocess.CompletedProcess(cmd, 0, stdout="nothing", stderr=""),
    )
    result = _call_result(
        server,
        "specproof_verify",
        {"repo": str(repo), "base_ref": "b", "head_ref": "h", "spec_text": "x"},
    )
    assert "unparseable" in _error_text(result)


def test_verify_timeout_maps_to_tool_error(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)

    def boom(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, 1800)

    monkeypatch.setattr(mcp_tools.subprocess, "run", boom)
    result = _call_result(
        server,
        "specproof_verify",
        {"repo": str(repo), "base_ref": "b", "head_ref": "h", "spec_text": "x"},
    )
    assert "timed out" in _error_text(result)


# ── specproof_contracts_list ────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: list[Any] = []

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        self.sql = sql
        self.params = list(params or [])

    def fetchall(self) -> list[dict[str, Any]]:
        return _FakeMySQLStore.rows


class _FakeConn:
    def __init__(self) -> None:
        self._cursor = _FakeCursor()
        self.cursor_called = False

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakeMySQLStore:
    rows: list[dict[str, Any]] = []
    down = False

    def __init__(self) -> None:
        pass

    @contextmanager
    def connection(self) -> Any:
        if _FakeMySQLStore.down:
            raise ConnectionError("mysql down")
        yield _FakeConn()


@pytest.fixture()
def fake_mysql(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeMySQLStore.rows = []
    _FakeMySQLStore.down = False
    monkeypatch.setattr("storage.mysql.MySQLStore", _FakeMySQLStore)


def test_contracts_list_returns_rows(
    server: SpecProofMCPServer, fake_mysql: None
) -> None:
    _FakeMySQLStore.rows = [
        {"id": "AUTH-01", "status": "APPROVED", "repo_path": "/r", "requirement": "auth"},
    ]
    payload = _payload(_call_result(server, "specproof_contracts_list", {"status": "approved"}))
    assert payload["degraded"] is False
    assert payload["count"] == 1
    assert payload["contracts"][0]["id"] == "AUTH-01"
    assert payload["filter"] == {"status": "approved", "repo_path": None}


def test_contracts_list_invalid_status_is_error(server: SpecProofMCPServer) -> None:
    result = _call_result(server, "specproof_contracts_list", {"status": "bogus"})
    assert "status must be one of" in _error_text(result)


def test_contracts_list_mysql_down_is_degraded(
    server: SpecProofMCPServer, fake_mysql: None
) -> None:
    _FakeMySQLStore.down = True
    payload = _payload(_call_result(server, "specproof_contracts_list", {}))
    assert payload["degraded"] is True
    assert "mysql unavailable" in payload["degraded_reason"]
    assert payload["contracts"] == []
    assert payload["count"] == 0


# ── specproof_eval_summary ──────────────────────────────────────────────────


def test_eval_summary_reads_persisted_report(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "eval.json"
    report.write_text(
        json.dumps({
            "total_cases": 20, "should_detect": 12, "detected": 12,
            "false_positives": 0, "precision": 100.0, "recall": 100.0, "f1": 100.0,
            "cases": [{"verdict": "PASS"}, {"verdict": "PASS"}, {"verdict": "FAIL"}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("SPECPROOF_EVAL_REPORT_PATH", str(report))
    payload = _payload(_call_result(server, "specproof_eval_summary", {}))
    assert payload["total_cases"] == 20
    assert payload["precision"] == 100.0
    assert payload["recall"] == 100.0
    assert payload["f1"] == 100.0
    assert payload["case_verdicts"] == {"PASS": 2, "FAIL": 1}


def test_eval_summary_missing_report_is_error(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECPROOF_EVAL_REPORT_PATH", str(tmp_path / "absent.json"))
    result = _call_result(server, "specproof_eval_summary", {})
    assert "No evaluation report" in _error_text(result)


def test_eval_summary_unreadable_report_is_error(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    monkeypatch.setenv("SPECPROOF_EVAL_REPORT_PATH", str(bad))
    result = _call_result(server, "specproof_eval_summary", {})
    assert "unreadable" in _error_text(result)


# ── specproof_craft_plan ────────────────────────────────────────────────────


def test_craft_plan_returns_steps_from_plan_json(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)

    def fake_run_cli(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        assert "--no-llm" in cmd, "MCP craft plan must stay deterministic (M1)"
        out_dir = Path(cmd[cmd.index("--output") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        plan = {
            "task_title": "新增接口",
            "mode": "deterministic",
            "llm_fallback_reason": "",
            "risk_classification": {"auth": False, "public_api": True},
            "budget_alloc": {"steps": 12, "per_step_iterations": 3},
            "steps": [
                {
                    "id": "1-understand",
                    "kind": "understand",
                    "target_files": ["src/api.py"],
                    "intent": "阅读目标代码",
                    "success_criteria": {"type": "grep", "value": "def "},
                    "deps": [],
                }
            ],
        }
        (out_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="SpecCraft", stderr="")

    monkeypatch.setattr(mcp_tools, "_run_cli", fake_run_cli)
    payload = _payload(
        _call_result(server, "specproof_craft_plan", {"spec_text": "加一个接口", "repo": str(repo)})
    )
    assert payload["mode"] == "deterministic"
    assert payload["task_title"] == "新增接口"
    assert payload["step_count"] == 1
    step = payload["steps"][0]
    assert step["id"] == "1-understand"
    assert step["success_criteria"] == {"type": "grep", "value": "def "}
    assert payload["plan_path"].endswith("plan.json")


def test_craft_plan_nonzero_exit_is_error(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(
        mcp_tools,
        "_run_cli",
        lambda cmd, timeout: subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="spec 解析失败"
        ),
    )
    result = _call_result(
        server, "specproof_craft_plan", {"spec_text": "x", "repo": str(repo)}
    )
    assert "exited with code 1" in _error_text(result)


def test_craft_plan_missing_plan_json_is_error(
    server: SpecProofMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(
        mcp_tools,
        "_run_cli",
        lambda cmd, timeout: subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr=""),
    )
    result = _call_result(
        server, "specproof_craft_plan", {"spec_text": "x", "repo": str(repo)}
    )
    assert "plan.json is missing" in _error_text(result)


# ── specproof_health ────────────────────────────────────────────────────────


class _ReadyStore:
    def __init__(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True


class _DownStore:
    def __init__(self) -> None:
        pass

    def is_ready(self) -> bool:
        raise ConnectionError("dependency down")


@pytest.fixture()
def fake_health_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    pairs = [
        ("storage.mysql", "MySQLStore"),
        ("storage.mongodb", "MongoDBStore"),
        ("storage.elasticsearch", "ElasticsearchStore"),
        ("storage.redis", "RedisStore"),
        ("storage.rabbitmq", "RabbitMQClient"),
        ("storage.minio", "MinIOClient"),
    ]
    for module, cls in pairs:
        monkeypatch.setattr(f"{module}.{cls}", _ReadyStore)


def test_health_all_ready(server: SpecProofMCPServer, fake_health_stores: None) -> None:
    payload = _payload(_call_result(server, "specproof_health", {}))
    assert payload["status"] == "ok"
    assert payload["degraded"] is False
    assert set(payload["checks"]) == {
        "mysql", "mongodb", "elasticsearch", "redis", "rabbitmq", "minio",
    }
    for check in payload["checks"].values():
        assert check["ok"] is True
        assert check["latency_ms"] >= 0


def test_health_degrades_honestly_when_dependency_down(
    server: SpecProofMCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("storage.redis.RedisStore", _DownStore)
    monkeypatch.setattr("storage.mysql.MySQLStore", _ReadyStore)
    monkeypatch.setattr("storage.mongodb.MongoDBStore", _ReadyStore)
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", _ReadyStore)
    monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", _ReadyStore)
    monkeypatch.setattr("storage.minio.MinIOClient", _ReadyStore)
    payload = _payload(_call_result(server, "specproof_health", {}))
    assert payload["status"] == "degraded"
    assert payload["degraded"] is True
    assert payload["checks"]["redis"]["ok"] is False
    assert "dependency down" in payload["checks"]["redis"]["error"]


# ── specproof_replay_info ───────────────────────────────────────────────────

MANIFEST = {
    "finding_id": "AUTH-01",
    "severity": "BLOCKER",
    "confidence": 0.95,
    "contract_id": "AUTH-01",
    "evidence_type": "differential_test",
    "evidence_digest": "sha256:abc",
    "blocker_check": {"all_blocker_conditions_met": True},
}


@pytest.fixture()
def capsule_dir_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    capsule_root = tmp_path / "capsules"
    capsule_root.mkdir()
    monkeypatch.setenv("SPECPROOF_CAPSULE_DIR", str(capsule_root))
    return capsule_root


def test_replay_info_reads_extracted_capsule(
    server: SpecProofMCPServer, capsule_dir_env: Path
) -> None:
    capsule = capsule_dir_env / "capsule-COURT-AUTH-01"
    capsule.mkdir()
    (capsule / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (capsule / "requirement.json").write_text("{}", encoding="utf-8")
    payload = _payload(
        _call_result(server, "specproof_replay_info", {"capsule_name": "capsule-COURT-AUTH-01"})
    )
    assert payload["found"] is True
    assert payload["kind"] == "directory"
    assert "manifest.json" in payload["listing"]
    assert payload["manifest"]["severity"] == "BLOCKER"
    assert payload["manifest"]["evidence_type"] == "differential_test"


def test_replay_info_reads_capsule_zip(
    server: SpecProofMCPServer, capsule_dir_env: Path
) -> None:
    zip_path = capsule_dir_env / "capsule-COURT-AUTH-01.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(MANIFEST))
        archive.writestr("generated-tests/Test.java", "class Test {}")
    payload = _payload(
        _call_result(server, "specproof_replay_info", {"capsule_name": "capsule-COURT-AUTH-01"})
    )
    assert payload["found"] is True
    assert payload["kind"] == "zip"
    assert payload["manifest"]["finding_id"] == "AUTH-01"
    assert "generated-tests" in payload["listing"]


def test_replay_info_path_traversal_rejected(server: SpecProofMCPServer) -> None:
    for bad in ("../etc/passwd", "a/b", "..", r"C:\evil", "name with spaces"):
        result = _call_result(server, "specproof_replay_info", {"capsule_name": bad})
        assert "invalid capsule name" in _error_text(result)


def test_replay_info_missing_capsule_lists_available(
    server: SpecProofMCPServer, capsule_dir_env: Path
) -> None:
    (capsule_dir_env / "capsule-SRC-UNIQUE-GUAR").mkdir()
    (capsule_dir_env / "capsule-SRC-UNIQUE-GUAR" / "manifest.json").write_text(
        json.dumps(MANIFEST), encoding="utf-8"
    )
    result = _call_result(
        server, "specproof_replay_info", {"capsule_name": "capsule-NOPE-01"}
    )
    text = _error_text(result)
    assert "not found" in text
    assert "capsule-SRC-UNIQUE-GUAR" in text


# ── Real stdio subprocess smoke ─────────────────────────────────────────────


def test_stdio_subprocess_end_to_end(tmp_path: Path) -> None:
    """Feed initialize/tools-list/tools-call over real stdin, read stdout."""
    messages = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
        + json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "specproof_eval_summary", "arguments": {}},
        })
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "cli.specproof.main", "mcp", "serve"],
        input=messages,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) >= 3, proc.stdout
    first = json.loads(lines[0])
    assert first["id"] == 1
    assert first["result"]["protocolVersion"] == "2024-11-05"
    second = json.loads(lines[1])
    assert len(second["result"]["tools"]) >= 6
    third = json.loads(lines[2])
    # Real repository state: the eval report may exist (summary) or be
    # missing (clear isError) - both are honest answers, never a crash.
    assert third["result"]["content"][0]["type"] == "text"
    if third["result"].get("isError"):
        assert "evaluation report" in third["result"]["content"][0]["text"].lower()
    else:
        payload = json.loads(third["result"]["content"][0]["text"])
        assert "total_cases" in payload
