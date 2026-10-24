"""`scripts/p0_5_closed_loop.py::security_scan` 的返回契约（#442 去重后由委托产生）。

#442 把脚本里**手抄的那份**秘密扫描删掉，改为委托 `agent.security_scanner`。
委托版必须继续交出调用方认的那几个键，否则报告段的打印和
`report["12_security_scan"]` 判定会直接 KeyError。本门钉住这个契约，并用一棵
临时树证明它**真的在扫描**——而不是交个空字典假绿。

顺带钉住一件 #442 的实质收益：旧手抄版只有 10 条 pattern，漏了 AWS Access Key
ID 等 5 类；委托版有 15 条，所以这里 planted 的 `AKIA…` 必须被抓到。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "p0_5_closed_loop.py"

#: 调用方（报告段与 report["12_security_scan"] 判定）实际读取的键。
CONTRACT_KEYS = {
    "passed",
    "scanned_files",
    "total_findings",
    "critical_count",
    "high_count",
    "findings",
    "canary_injected",
    "canary_detected",
}


def _load_script() -> ModuleType:
    """Load the closed-loop script as a module (it guards LLM_API_KEY at import)."""
    spec = importlib.util.spec_from_file_location("p0_5_closed_loop_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses/attrs look the module up by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def loop_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-a-real-secret")
    return _load_script()


def test_security_scan_returns_the_contract_the_report_section_reads(
    loop_module: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "aws.txt").write_text("AKIA" + "Q" * 16 + "\n", encoding="utf-8")
    scan = loop_module.security_scan(str(tmp_path))

    assert set(scan) >= CONTRACT_KEYS, f"missing keys: {CONTRACT_KEYS - set(scan)}"
    # 真的在扫，而且扫的是委托后的 15 条 pattern（旧手抄版漏掉的那 5 类之一）
    assert any(f["pattern"] == "AWS Access Key ID" for f in scan["findings"])
    assert scan["critical_count"] == 0
    assert scan["high_count"] == 1
    assert scan["passed"] is False
    # canary 自测的两半都为真，否则 report["12_security_scan"] 会被判 FAIL
    assert scan["canary_injected"] is True
    assert scan["canary_detected"] is True


def test_security_scan_skips_placeholders_and_passes_a_clean_tree(
    loop_module: ModuleType, tmp_path: Path
) -> None:
    """占位符不算 secret；干净树必须 passed —— 否则门永远红，等于没门。"""
    (tmp_path / "app.yml").write_text(
        'api_key: "your_api_key_here_12345"\npassword: "replace_me"\n', encoding="utf-8"
    )
    scan = loop_module.security_scan(str(tmp_path))
    assert scan["findings"] == []
    assert scan["passed"] is True


def test_the_script_no_longer_carries_its_own_pattern_table() -> None:
    """#442 的去重要真的发生了：脚本里不该再有手抄的 pattern 表 / canary 常量。

    用 AST 读**绑定**，不读文本：这段解释性注释自己就提到了那两个名字，子串检查
    会被自己的注释判红（本仓库为这类假红栽过，纪律是「探针读绑定，不读文本」）。
    """
    import ast

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigned.update(
                t.id for t in node.targets if isinstance(t, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigned.add(node.target.id)

    assert "_SECRET_PATTERNS" not in assigned
    assert "CANARY_SECRET" not in assigned

    # 并且它确实委托了模块（读导入绑定，同样不读注释）
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "run_full_security_scan" in imported
