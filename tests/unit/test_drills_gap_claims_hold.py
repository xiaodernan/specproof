"""DRILLS.md 的缺口声称必须与代码事实双向一致 — #129 / FIX-20.

§6 自称"如实标注, 均给出精确缺口位置"。#129 复核时实测出四处写下即为假的声称
(回收器 / WAITING_FOR_PROVIDER 接线 / 吊销端点), 另有两处已过期 (§6 第 2 行的
"回收待开发"、两个 gap audit 的 "OIDC logout ⏳")。人工记账挡不住下一次漂移, 所以把
**仍然成立**的那些声称绑到代码事实上, 两个方向都钉:

* 代码先动 (真的把缺口实现了, 或撤掉已登记的能力) → 红, 迫使台账同批更正;
* 台账先动 (把已落地的能力改回"需开发", 或抹掉更正标记) → 同样红。

假句按 FIX-14 规矩保留在原文里: 门只要求它们与"更正"标记同行, 抹掉假句本身也判红 —
那等于把这次复核的证据一起抹掉。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DRILLS = REPO / "docs" / "operations" / "DRILLS.md"
GAP_AUDITS = (
    REPO / "docs" / "architecture" / "GUIDE_GAP_AUDIT.md",
    REPO / "docs" / "architecture" / "AGENT_PLAN_GAP_AUDIT.md",
)
WORKER_SOURCE = REPO / "agent" / "worker.py"

#: Sentences this ledger once printed as facts and that were later proved false.
#: They stay on the page (FIX-14); only an uncorrected restatement is a failure.
FALSE_GAP_CLAIMS = (
    "该回收器未实现",
    "从未转入该可恢复态",
    "api/ 实测 0 命中",
    "api/ 无 logout",
    "仍缺的是把该行捞回来的回收器",
)


def _drills_lines() -> list[str]:
    return DRILLS.read_text(encoding="utf-8").splitlines()


def _row(prefix: str) -> str:
    matches = [line for line in _drills_lines() if line.startswith(prefix)]
    assert len(matches) == 1, f"{prefix!r} matched {len(matches)} rows"
    return matches[0]


def _uncorrected_false_claims(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if any(phrase in line for phrase in FALSE_GAP_CLAIMS) and "更正" not in line
    ]


def _app_routes() -> dict[str, set[str]]:
    """The published contract — OpenAPI sees through the lazy sub-routers.

    `app.routes` still holds FastAPI's `_IncludedRouter` wrappers at this
    point, so walking it would "find" no application routes at all and the
    gate below would be green while the endpoint is missing.
    """
    from api.server import app

    paths = app.openapi()["paths"]
    return {
        path: {method.upper() for method in methods}
        for path, methods in paths.items()
    }


def test_false_gap_claims_may_only_appear_next_to_their_correction() -> None:
    text = DRILLS.read_text(encoding="utf-8")
    uncorrected = _uncorrected_false_claims(text)
    assert uncorrected == [], uncorrected
    # The false sentences themselves must survive: correcting is not erasing.
    for phrase in FALSE_GAP_CLAIMS:
        assert phrase in text, f"{phrase!r} was deleted instead of corrected"
    # Same rule for the two gap audits, which printed the logout claim too.
    for path in GAP_AUDITS:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "OIDC logout" in line:
                assert "更正" in line, f"{path.name} restates the logout gap uncorrected"


def test_the_false_claim_detector_is_not_vacuous() -> None:
    stale = "| revoke | OIDC 会话注销 | 无 logout/revoke 端点 (api/ 实测 0 命中) | ⏳ 需开发 |"
    assert _uncorrected_false_claims(stale) == [stale]
    corrected = stale + " **更正 (2026-09-28, #129)**: 原句为假 — 已落地"
    assert _uncorrected_false_claims(corrected) == []
    # Reverse control: describing the shipped endpoint is not a gap claim.
    shipped = "| revoke | OIDC 会话注销 | 会话注销现为 `POST /auth/logout` | ✅ 可执行 |"
    assert _uncorrected_false_claims(shipped) == []


def test_logout_endpoint_is_registered_and_the_ledger_says_so() -> None:
    routes = _app_routes()
    assert "POST" in routes.get("/auth/logout", set()), (
        "POST /auth/logout 不在路由表里, 而 §6 第 3 行写着 ✅"
    )
    row = _row("| 3 | OIDC 会话注销/令牌吊销端点")
    assert "✅" in row and "#129" in row, row
    # The row points readers at this gate; the gate must really be the file it names.
    assert "test_drills_gap_claims_hold.py" in row


def test_the_s4_revoke_rows_name_endpoints_that_really_exist() -> None:
    routes = _app_routes()
    logout_row = _row("| revoke | OIDC 会话注销/令牌吊销")
    assert "POST /auth/logout" in logout_row and "✅" in logout_row
    token_row = _row("| revoke 撤销 | 撤销租户/用户 API Token")
    assert "DELETE /api/v1/admin/tokens/{token_id}" in token_row and "✅" in token_row
    # Both promises of that table row are routed, not merely written down.
    assert "POST" in routes.get("/auth/logout", set())
    assert "DELETE" in routes.get("/api/v1/admin/tokens/{token_id}", set())


def test_certificate_revocation_gap_still_matches_the_evidence_tree() -> None:
    revoking = [
        path
        for path in (REPO / "evidence").rglob("*.py")
        if "revoke" in path.read_text(encoding="utf-8", errors="replace").lower()
    ]
    row = _row("| 4 | Merge Certificate 撤销")
    if revoking:
        pytest.fail(
            f"evidence/ 已长出撤销能力 {revoking} — §6 第 4 行仍写着 ⏳, 请同批更正"
        )
    assert "⏳" in row and "evidence/" in row, row


def test_provider_signal_residue_matches_the_worker_source() -> None:
    source = WORKER_SOURCE.read_text(encoding="utf-8")
    body = re.search(
        r"def _reclaim_once\(self\) -> ReclaimPass:(?P<body>.*?)(?=\r?\n    def )",
        source,
        re.S,
    )
    assert body is not None, "找不到 Worker._reclaim_once, 残留说法无从核对"
    assert "provider_ready" not in body.group("body"), (
        "_reclaim_once 现在传 provider_ready 了 — §6 第 1/2 行的残留说法过期, 请同批更正"
    )
    signature = re.search(r"def run_reclaim_pass\([^)]*\)", source, re.S)
    assert signature is not None and "provider_ready" in signature.group(0)
    assert "def recover_waiting_for_provider_jobs(" in source
    row1 = _row("| 1 | 崩溃作业自动回收器")
    row2 = _row("| 2 | WAITING_FOR_PROVIDER 接线")
    assert "provider" in row1 and ("信号" in row1 or "provider_ready" in row1), row1
    assert "provider_ready" in row2, row2
    assert "回收待开发" not in row2, "§6 第 2 行还在说'回收待开发', 而回收器早已存在"


def test_the_auth_readme_lists_every_published_auth_operation() -> None:
    """docs/api/auth/README.md 是读者最先遇到的端点清单 — 两个方向都钉."""
    routes = _app_routes()
    readme = (REPO / "docs" / "api" / "auth" / "README.md").read_text(encoding="utf-8")
    published = sorted(path for path in routes if path.startswith("/auth/"))
    assert published, "OpenAPI 里没有 /auth/ 路径, 这条门会假绿"
    for path in published:
        assert path in readme, f"{path} 没写进 docs/api/auth/README.md 的端点清单"
    # Reverse direction: a documented /auth/ path must be a real operation,
    # except the two flow endpoints deliberately hidden from the schema.
    hidden = {"/auth/oidc/login", "/auth/oidc/callback"}
    mentioned = set(re.findall(r"/auth/[a-z_/{}]*", readme))
    unknown = mentioned - set(routes) - hidden
    assert not unknown, unknown
    assert "`POST /auth/logout`" in readme


def test_web_logout_gap_matches_the_web_source() -> None:
    wired = [
        path
        for pattern in ("*.ts", "*.tsx")
        for path in (REPO / "apps" / "web" / "src").rglob(pattern)
        if "auth/logout" in path.read_text(encoding="utf-8", errors="replace")
    ]
    row9 = _row("| 9 | Web 退出入口接")
    # If wired, verify the DRILLS.md status reflects completion
    if wired:
        assert "✅" in row9 and "已接线" in row9, (
            f"Web 已经接上 auth/logout {wired} — §6 第 9 行应标记为 ✅ 已接线"
        )
        return
    # If not wired, verify it still says pending
    assert "待接线" in row9 and "App.tsx:131" in row9, row9
    # The button that does exist must be credited, not described as missing.
    app_source = (REPO / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "logout" in app_source, "退出按钮不见了, 而第 9 行写着按钮已存在"
    assert "无登出" not in row9 and "无退出" not in row9, row9
