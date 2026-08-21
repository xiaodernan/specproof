"""Offline end-to-end tests for the SWE-bench-Lite harness (no network, no Docker).

These tests prove the harness mechanics on the bundled sample:
- one instance resolves deterministically via the sample-only hardcoded fix;
- one instance stays honestly unresolved ("no fix produced");
- the results JSON obeys the honesty schema (reason non-empty iff unresolved);
- dataset errors refuse loudly instead of fabricating results.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "scripts" / "bench_swebench.py"
SAMPLE_DIR = REPO_ROOT / "scripts" / "swebench_sample"
SAMPLE_INSTANCES = SAMPLE_DIR / "instances.json"

RESOLVED_ID = "specproof__toycalc-double-1"
UNRESOLVED_ID = "specproof__toycalc-multiply-1"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BENCH_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def load_results(output: Path) -> dict[str, Any]:
    payload: Any = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_offline_sample_end_to_end(tmp_path: Path) -> None:
    """--offline 完整跑通: 1 resolved + 1 honest unresolved, 全 schema 断言。"""
    output = tmp_path / "results.json"
    proc = run_cli("--offline", "--output", str(output))
    assert proc.returncode == 0, proc.stderr
    payload = load_results(output)
    assert payload["schema_version"] == "1.0"
    assert payload["mode"] == "deterministic"
    assert payload["dataset"]["kind"] == "offline-sample"
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["resolved"] == 1
    assert payload["summary"]["unresolved"] == 1
    assert payload["summary"]["resolved_rate_pct"] == 50.0

    instances = payload["instances"]
    assert isinstance(instances, list) and len(instances) == 2
    by_id = {entry["instance_id"]: entry for entry in instances}

    resolved = by_id[RESOLVED_ID]
    assert resolved["resolved"] is True
    assert resolved["status"] == "resolved"
    assert resolved["reason"] == ""
    assert resolved["checkout"]["method"] == "copy"
    craft = resolved["craft"]
    assert craft["result"] == "DONE"
    assert craft["edits"] == ["calc.py"]
    assert resolved["test_patch"]["applied"] is True
    assert [test["test"] for test in resolved["fail_to_pass"]] == [
        "test_calc.py::test_double",
        "test_hidden.py::test_double_negative",
    ]
    assert all(test["outcome"] == "passed" for test in resolved["fail_to_pass"])
    assert all(test["outcome"] == "passed" for test in resolved["pass_to_pass"])
    assert Path(resolved["logs"]["tests_log"]).is_file()

    unresolved = by_id[UNRESOLVED_ID]
    assert unresolved["resolved"] is False
    assert unresolved["status"] == "unresolved"
    assert "no fix produced" in unresolved["reason"]
    assert unresolved["craft"] is None
    assert unresolved["test_patch"]["applied"] is False

    # Honesty schema: reason 恰好只在非 resolved 记录上非空。
    for entry in instances:
        if entry["resolved"]:
            assert entry["reason"] == ""
        else:
            assert entry["reason"].strip()


def test_dataset_file_path_runs_sample(tmp_path: Path) -> None:
    """--dataset <本地 JSON> 路径分支与 --offline 给出同一结果。"""
    output = tmp_path / "results.json"
    proc = run_cli("--dataset", str(SAMPLE_INSTANCES), "--output", str(output))
    assert proc.returncode == 0, proc.stderr
    payload = load_results(output)
    assert payload["dataset"]["kind"] == "file"
    assert payload["summary"]["resolved"] == 1
    assert payload["summary"]["unresolved"] == 1


def test_missing_dataset_refuses_loudly(tmp_path: Path) -> None:
    """数据集不存在 → 清晰报错 + exit 2, 不产出任何结果文件 (绝不伪造)。"""
    output = tmp_path / "results.json"
    proc = run_cli(
        "--dataset", str(tmp_path / "no-such-file.json"), "--output", str(output)
    )
    assert proc.returncode == 2
    assert "offline" in proc.stderr.lower()
    assert not output.exists()


def test_invalid_instance_recorded_unresolved(tmp_path: Path) -> None:
    """schema 不合法的实例 → 诚实 unresolved 记录, 不崩溃不伪造。"""
    dataset = tmp_path / "bad.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "instance_id": "owner__repo-1",
                    "repo": str(SAMPLE_DIR / "repos" / "toycalc-double"),
                    "base_commit": "sample-v1",
                    "problem_statement": "fix it",
                    "test_patch": "",
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "results.json"
    proc = run_cli("--dataset", str(dataset), "--output", str(output))
    assert proc.returncode == 0, proc.stderr
    payload = load_results(output)
    assert payload["summary"]["resolved"] == 0
    assert payload["summary"]["unresolved"] == 1
    record = payload["instances"][0]
    assert record["resolved"] is False
    assert "schema invalid" in record["reason"]


def test_sample_fix_registry_scoped_to_sample_ids() -> None:
    """硬编码 fix 只注册给样例实例 id — 永远够不到真实 SWE-bench 实例。"""
    spec = importlib.util.spec_from_file_location(
        "bench_swebench_under_test", BENCH_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = module.SAMPLE_FIX_REGISTRY
    sample_payload: Any = json.loads(SAMPLE_INSTANCES.read_text(encoding="utf-8"))
    sample_ids = {str(entry["instance_id"]) for entry in sample_payload}
    assert set(registry) <= sample_ids
    assert RESOLVED_ID in registry
    assert UNRESOLVED_ID not in registry
    assert all(str(key).startswith("specproof__") for key in registry)


def test_cli_help_lists_flags() -> None:
    proc = run_cli("--help")
    assert proc.returncode == 0
    assert "--offline" in proc.stdout
    assert "--mode" in proc.stdout
    assert "--fix-module" in proc.stdout
