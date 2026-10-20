"""specproof evidence — 证据链运维命令（阶段 2）。

三个子命令，都围绕「证据链是否还完整」：

``replay-batch``
    批量回放一批 Bug Capsule，产出可审计的批量记录：每个胶囊的结局、
    失败分类（环境 / 工件 / 脚本 / 分歧）和总体统计。

``verify-cert``
    离线验证一份证书：签名是否有效、摘要是否可算、是否被撤销、它命名
    的证据摘要是否真的在手上。不联网、不读数据库。

``scan``
    扫描对象链完整性：悬挂引用（记录指向的载荷没了）、孤儿载荷（文件
    在但没有记录）、摘要不符（记录后被改过）。只报告，不删除。

诚实规则（这三个命令存在的意义）：
- 未签名文档一律称为「摘要证明」，绝不称为「已签名证书」——措辞由
  evidence/offline_verify.py 的 describe_attestation_level() 统一给出。
- 批量回放的成功率分母是「已判定」的数量，不是批次大小：环境故障
  不是「没能复现」，它根本没有回放。
- 扫描只产出报告。删除是另一个动作，需要单独确认。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


@click.group("evidence")
def evidence_cmd() -> None:
    """证据链运维：批量回放 / 离线证书验证 / 对象链完整性扫描."""


# ── replay-batch ───────────────────────────────────────────────────────────


@evidence_cmd.command("replay-batch")
@click.argument(
    "capsule_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--repo",
    "repo_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="对每个胶囊回放所依据的 git 仓库（省略则只做工件检查，不执行）",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="批量记录 JSON 的写出路径（默认写到当前目录）",
)
@click.option("--timeout", "run_timeout", type=int, default=900, show_default=True,
              help="每个胶囊的沙箱超时秒数")
@click.option("--json", "as_json", is_flag=True, help="只输出机器可读 JSON")
def replay_batch(
    capsule_dir: Path,
    repo_dir: Path | None,
    output_path: Path | None,
    run_timeout: int,
    as_json: bool,
) -> None:
    """批量回放 CAPSULE_DIR 下的所有胶囊并汇总结果。"""
    from evidence.batch_replay import (
        BatchReplayRunner,
        discover_capsules,
        write_batch_record,
    )

    capsules = discover_capsules(capsule_dir)
    if not capsules:
        click.echo(f"ERROR: no capsule .zip found under {capsule_dir}", err=True)
        raise SystemExit(1)

    if repo_dir is None:
        # Without a repository there is nothing to execute against: the
        # honest answer is "not run", not "0 % success".
        click.echo(
            "ERROR: --repo is required to replay a capsule (a capsule is "
            "executed against a repository; without one nothing was judged)",
            err=True,
        )
        raise SystemExit(1)

    runner = BatchReplayRunner(timeout=run_timeout)
    record = runner.run(capsules, repo_dir)
    target = output_path or Path("batch-replay-report.json")
    written = write_batch_record(record, target)

    payload = record.to_dict()
    if as_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        counts = payload["by_outcome"]
        click.echo(f"Capsules: {payload['total']}")
        click.echo(f"Judged:   {payload['judged']}  (unjudged: {payload['unjudged']})")
        rate = payload["success_rate"]
        click.echo(
            "Reproduced rate: " + ("未判定 (没有胶囊产生结论)" if rate is None
                                     else f"{rate * 100:.1f}%")
        )
        click.echo("By outcome:")
        for name, count in counts.items():
            click.echo(f"  {name}: {count}")
        click.echo(f"Report: {written}")

    # A batch that could not judge anything is not a pass.
    if payload["judged"] == 0:
        raise SystemExit(1)


# ── verify-cert ────────────────────────────────────────────────────────────


@evidence_cmd.command("verify-cert")
@click.argument(
    "certificate",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--public-key",
    "public_key",
    default=None,
    help="期望的 Ed25519 公钥（hex）。省略时签名不会被检查，结果只能是未验证。",
)
@click.option(
    "--evidence-digest",
    "known_digests",
    multiple=True,
    help="已持有的证据摘要（可重复）。用于检查证书命名的证据是否真的在手上。",
)
@click.option("--json", "as_json", is_flag=True, help="只输出机器可读 JSON")
def verify_cert(
    certificate: Path,
    public_key: str | None,
    known_digests: tuple[str, ...],
    as_json: bool,
) -> None:
    """离线验证一份证书文件（不联网、不读数据库）。"""
    from evidence.offline_verify import (
        describe_attestation_level,
        verify_certificate_offline,
    )

    try:
        statement = json.loads(certificate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        click.echo(f"ERROR: certificate could not be read: {exc}", err=True)
        raise SystemExit(1) from exc

    report = verify_certificate_offline(
        statement,
        public_key=public_key,
        known_evidence_digests=list(known_digests),
    )
    payload = report.to_dict()

    if as_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Verdict:  {report.verdict}")
        click.echo(f"Level:    {report.attestation_level}")
        click.echo(f"Meaning:  {describe_attestation_level(report.attestation_level)}")
        click.echo(f"Digest:   {report.certificate_digest or 'N/A'}")
        click.echo(f"Subject:  {report.subject_repository} @ {report.subject_commit_sha}")
        click.echo(f"Revoked:  {report.revoked}")
        if report.missing_evidence:
            click.echo(
                f"Missing evidence digests: {len(report.missing_evidence)}"
            )
        for note in report.notes:
            click.echo(f"  note: {note}")

    if report.verdict == "valid":
        return
    raise SystemExit(1)


# ── scan ───────────────────────────────────────────────────────────────────


@evidence_cmd.command("scan")
@click.argument(
    "root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="扫描报告 JSON 的写出路径（默认写到当前目录）",
)
@click.option("--json", "as_json", is_flag=True, help="只输出机器可读 JSON")
def scan(root: Path, output_path: Path | None, as_json: bool) -> None:
    """扫描对象链：悬挂引用 / 孤儿载荷 / 摘要不符（只报告，不删除）。"""
    from evidence.orphan_scan import scan_object_chain, write_scan_report
    from storage.object_metadata import default_object_metadata_store

    try:
        store = default_object_metadata_store()
    except Exception as exc:  # noqa: BLE001 — the store may need MySQL
        click.echo(
            f"ERROR: the object metadata store is unavailable: {exc}\n"
            "       (the scan needs the store to know what SHOULD exist)",
            err=True,
        )
        raise SystemExit(1) from exc

    report = scan_object_chain(store, root)
    target = output_path or Path("object-chain-scan.json")
    written = write_scan_report(report, target)

    payload: dict[str, Any] = report.to_dict()
    if as_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Records scanned: {payload['scanned_records']}")
        click.echo(f"Files scanned:   {payload['scanned_files']}")
        click.echo("Findings:")
        for name, count in payload["by_kind"].items():
            click.echo(f"  {name}: {count}")
        for finding in payload["findings"]:
            click.echo(f"  - [{finding['kind']}] {finding['path']}: {finding['detail']}")
        click.echo(f"Report: {written}")

    if not report.is_clean():
        raise SystemExit(1)


__all__ = ["evidence_cmd"]
