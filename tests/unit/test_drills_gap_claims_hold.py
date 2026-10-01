"""DRILLS.md 的缺口声称必须与代码事实双向一致 — #129 / FIX-20.

§6 自称"如实标注, 均给出精确缺口位置"。#129 复核时实测出四处写下即为假的声称
(回收器 / WAITING_FOR_PROVIDER 接线 / 吊销端点), 另有两处已过期 (§6 第 2 行的
"回收待开发"、两个 gap audit 的 "OIDC logout ⏳")。人工记账挡不住下一次漂移, 所以把
**仍然成立**的那些声称绑到代码事实上, 两个方向都钉:

* 代码先动 (真的把缺口实现了, 或撤掉已登记的能力) → 红, 迫使台账同批更正;
* 台账先动 (把已落地的能力改回"需开发", 或抹掉更正标记) → 同样红。

假句按 FIX-14 规矩保留在原文里: 门只要求它们与"更正"标记同行, 抠掉假句本身也判红 —
那等于把这次复核的证据一起抹掉。#138 再补两条撤销方向的假句与三条新门 (端点↔证据↔台账、
§3 计数↔表、消费方零调用点↔第 10 行)。
"""

from __future__ import annotations

import re
from pathlib import Path

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
    "evidence/ 无撤销能力",
    "evidence/ 无任何 revoke/吊销 能力",
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
    cert_row = _row("| revoke | Merge Certificate 撤销")
    assert "POST /api/v1/admin/certificates/revoke" in cert_row and "✅" in cert_row
    # Both promises of that table row are routed, not merely written down.
    assert "POST" in routes.get("/auth/logout", set())
    assert "DELETE" in routes.get("/api/v1/admin/tokens/{token_id}", set())
    assert "POST" in routes.get("/api/v1/admin/certificates/revoke", set())
    assert "GET" in routes.get("/api/v1/admin/certificates/revocations", set())


def test_certificate_revocation_gap_still_matches_the_evidence_tree() -> None:
    """#138: evidence 能力 ↔ OpenAPI 端点 ↔ §6 第 4 行, 三个方向都钉."""
    routes = _app_routes()
    revoking = [
        path
        for path in (REPO / "evidence").rglob("*.py")
        if "revoke" in path.read_text(encoding="utf-8", errors="replace").lower()
    ]
    row = _row("| 4 | Merge Certificate 撤销")
    routed = "POST" in routes.get("/api/v1/admin/certificates/revoke", set())
    capability = bool(revoking)
    assert routed == capability, (
        f"evidence/ 撤销能力={capability} 与 OpenAPI 端点={routed} 不一致 — "
        "端点在而证据不在, 或证据在而端点没注册"
    )
    if capability:
        assert "✅" in row and "#138" in row, row
        assert "⏳" not in row, f"能力已存在, §6 第 4 行却仍写 ⏳: {row}"
        assert "test_certificate_revocation_gap_still_matches_the_evidence_tree" in row
        # 签发侧 ✅ 不许顺手把没接的消费方也说成 ✅: 第 10 行必须仍在⏳。
        row10 = _row("| 10 | 已撤销证书的消费方拦截")
        assert "⏳" in row10, row10
    else:
        assert "⏳" in row, f"evidence/ 撤销能力没了, §6 第 4 行却不是 ⏳: {row}"

def test_provider_signal_residue_matches_the_worker_source() -> None:
    source = WORKER_SOURCE.read_text(encoding="utf-8")
    # The tick passes the hold window; the pass builds the DB probe (#133).
    once = re.search(
        r"def _reclaim_once\(self\)[^:]*:(?P<body>.*?)(?=\r?\n    def )",
        source,
        re.S,
    )
    assert once is not None, "找不到 Worker._reclaim_once, 残留说法无从核对"
    assert "provider_hold_seconds" in once.group("body"), (
        "_reclaim_once 不再传递 hold 窗口 — §6 第 1/2 行的落地说法过期, 请同批更正"
    )
    signature = re.search(r"def run_reclaim_pass\([^)]*\)", source, re.S)
    assert signature is not None and "provider_hold_seconds" in signature.group(0)
    assert "WORKER_PROVIDER_HOLD_SECONDS" in source
    assert "def _fresh_park_hold_probe(" in source
    # The "no probe exists" sentence must be gone with the probe's arrival.
    assert "No model-provider health probe exists" not in source
    store_source = (REPO / "storage" / "mysql.py").read_text(encoding="utf-8")
    assert "def has_fresh_provider_park(" in store_source
    assert "NOW(3) - INTERVAL %s SECOND" in store_source
    row1 = _row("| 1 | 崩溃作业自动回收器")
    row2 = _row("| 2 | WAITING_FOR_PROVIDER 接线")
    assert "✅" in row1 and "#133" in row1, row1
    assert "provider_hold_seconds" in row1, row1
    assert "✅" in row2 and "#133" in row2, row2
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

# ── #138: 撤销的三处残留 (计数 / 消费方 / 台账句) ─────────────────────────────

#: Directories that are not the product tree when hunting for callers.
PRODUCT_SKIP = {
    ".venv", ".scratch", ".git", ".mypy_cache", ".ruff_cache", "node_modules",
    "tests", "demo", "artifacts", "build", "dist", "golden-cases", "__pycache__",
}

#: Files allowed to talk about revocations without being a *consumer* of it
#: (they define the capability or expose it): everything else that references
#: it is the wiring §6 第 10 行 says is missing.
REVOCATION_WRITERS = {
    REPO / "evidence" / "revocation_log.py",
    REPO / "evidence" / "certificate.py",
    REPO / "api" / "routes" / "admin.py",
}

#: Sentences that call certificate revocation absent, across every ledger.
REVOKE_GAP_MARKERS = (
    "证书撤销 ⏳",
    "撤销状态 ⛔",
    "撤销簿/CRL",
    "无撤销能力",
    "无任何 revoke/吊销 能力",
)


def _s3_table_rows() -> list[str]:
    """The §3.1 verb table, rows only (header + separator skipped)."""
    lines = _drills_lines()
    header = [
        i for i, line in enumerate(lines)
        if line.startswith("| 动词 | 事故响应动作 |")
    ]
    assert len(header) == 1, header
    rows: list[str] = []
    for line in lines[header[0] + 2:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    assert rows, "§3.1 表是空的, 计数门无从谈起"
    return rows


def _uncorrected_ledger_claim(line: str) -> bool:
    return any(marker in line for marker in REVOKE_GAP_MARKERS) and "更正" not in line \
        and "✅" not in line


def test_the_s3_headline_counts_are_the_table_counts() -> None:
    """§1/§3.2 的数字必须等于 §3.1 表的实数 — 过期数字也算假声称."""
    rows = _s3_table_rows()
    ok = sum(1 for row in rows if "✅" in row and "⏳" not in row)
    pending = sum(1 for row in rows if "⏳" in row)
    assert ok + pending == len(rows), (ok, pending, len(rows))
    lines = _drills_lines()
    headline = _row("| 3 | 安全响应桌面推演")
    main = [
        line for line in lines
        if line.startswith("- 暂停/冻结/撤销/隔离/保全的主干路径")
    ]
    gaps = [line for line in lines if "项缺口如实标注" in line]
    assert len(main) == 1 and len(gaps) == 1, (main, gaps)
    for line, exact, needed_when_stale in (
        (headline, f"{ok} 项可执行, {pending} 项需开发", (str(ok), str(pending))),
        (main[0], f"{ok} 行 ✅ 可执行", (str(ok),)),
        (gaps[0], f"{pending} 项缺口", (str(pending),)),
    ):
        if exact in line:
            continue
        # A stale number may stay only as a corrected quotation (FIX-14).
        assert "更正" in line, f"缺 {exact!r} 且无更正标记: {line[:160]}"
        assert all(token in line for token in needed_when_stale), line[:160]


def _product_py_files() -> list[Path]:
    """Product .py files: no venvs, no scratch worktrees, no fixtures."""
    files: list[Path] = []
    for path in REPO.rglob("*.py"):
        rel = path.relative_to(REPO)
        if PRODUCT_SKIP & set(rel.parts) or rel.parts[0].startswith("."):
            continue
        files.append(path)
    return files


def test_the_revocation_consumer_gap_is_pinned() -> None:
    """谁真的调用吊销判定, 谁就必须把 §6 第 10 行改成 ✅ — 两个方向."""
    needle = ("is_revoked(", "find_revocations(", "CertificateRevocation", "revocation_log")
    consumers = sorted(
        str(path.relative_to(REPO))
        for path in _product_py_files()
        if path not in REVOCATION_WRITERS
        and any(hit in path.read_text(encoding="utf-8", errors="replace") for hit in needle)
    )
    row = _row("| 10 | 已撤销证书的消费方拦截")
    if consumers:
        assert "✅" in row, (
            f"消费方已接线 {consumers} — §6 第 10 行仍写 ⏳, 请同批更正"
        )
    else:
        assert "⏳" in row, f"零调用点, 第 10 行却标 ✅: {row}"
        assert "零调用点" in row, row
        assert "test_the_revocation_consumer_gap_is_pinned" in row


def test_no_ledger_still_calls_certificate_revocation_absent() -> None:
    """四本台账里, 说撤销不存在的句子必须与"更正"同处一行."""
    ledgers = (
        DRILLS,
        *GAP_AUDITS,
        REPO / "docs" / "architecture" / "COMPLETION_MAP.md",
        REPO / "docs" / "architecture" / "EVOLUTION_GAP_MAP.md",
    )
    uncorrected = [
        f"{path.name}:{lineno}"
        for path in ledgers
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _uncorrected_ledger_claim(line)
    ]
    assert uncorrected == [], uncorrected
    # The detector is not vacuous: the pre-#138 sentence is caught, and the
    # corrected quotation of it is not.
    stale = "| x | y | 证书撤销 ⏳ (DRILLS 4 需开发) |"
    assert _uncorrected_ledger_claim(stale)
    assert not _uncorrected_ledger_claim(stale + " **更正 (#138)**: 已落地 |")
    assert not _uncorrected_ledger_claim("| x | y | 证书撤销簿 ✅ #138 |")
