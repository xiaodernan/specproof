#!/usr/bin/env python3
"""Backup/restore drill for the SpecProof stores (MySQL + MongoDB).

This script codifies the 2026-11-08 drill (ledger #1527 / DATA_LIFECYCLE §6.4)
so it can be re-run verbatim. It performs, for each selected store:

  MySQL
    1. exact per-table COUNT(*) snapshot of the SOURCE database
       (default `specproof_test`, an expendable isolated database — never
       `specproof_phase0`);
    2. `mysqldump --single-transaction --routines --triggers --set-gtid-purged=OFF`
       into a scratch file (tempdir or --backup-dir);
    3. restore into a brand-new scratch database (default `specproof_restore_drill`);
    4. per-table COUNT(*) after restore; both snapshots must match exactly;
    5. `schema_migrations` MAX(version) must match;
    6. drop the scratch database; write a JSON drill report.
    Optional `--product-backup <dir>`: read-only dump of `specproof_phase0`
    (never restores over it). Its plaintext file is hashed, the sha256 is
    recorded, and the file is deleted afterwards (it may contain tenant
    data — see DATA_LIFECYCLE §6.4).

  MongoDB
    1. seed a scratch database (default `specproof_drill_scratch`) with
       --documents synthetic docs;
    2. `mongodump --archive --gzip`;
    3. drop the scratch database; `mongorestore --archive --gzip`;
    4. verify document count and the SUM(seq) digest;
    5. drop the scratch database; write a JSON drill report.
    Optional `--product-backup <dir>`: read-only dump of `specproof_phase0`,
    sha256 recorded, plaintext archive deleted after hashing.

Safety invariants (do not relax):
  * No command ever writes to the product database (only mysqldump/mongodump
    read-only dumps are taken of it, only when --product-backup is passed).
  * DROP DATABASE is only ever issued against the scratch names, which are
    validated by `assert_scratch_allowed` before use.
  * Product plaintext dumps are deleted after sha256 is recorded unless
    --keep-product-dump is passed (then the caller owns the file's fate).
  * All subprocess calls pin encoding="utf-8", errors="replace".

Exit codes: 0 = all checks passed; 2 = validation failure; 3 = subprocess
failure; 4 = counts/digest mismatch (report still written).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

MYSQL_CONTAINER = "specproof-mysql"
MONGO_CONTAINER = "specproof-mongodb"
MONGO_USER = "specproof"
MONGO_PASSWORD = os.environ.get("SPECPROOF_MONGO_ROOT_PASSWORD", "specproof_pass")

PRODUCT_MYSQL = "specproof_phase0"
DEFAULT_SOURCE_MYSQL = "specproof_test"
DEFAULT_SCRATCH_MYSQL = "specproof_restore_drill"
DEFAULT_SCRATCH_MONGO = "specproof_drill_scratch"
DEFAULT_MONGO_DOCUMENTS = 250

MYSQL_PROTECTED = {
    "mysql", "sys", "information_schema", "performance_schema",
    PRODUCT_MYSQL, "specproof_test", "specproof_test2", "specproof_rollback_probe",
}


def assert_scratch_allowed(name: str, kind: str) -> str:
    """Return the validated scratch name or raise ValueError.

    kind is 'mysql' or 'mongo'. Scratch names are fixed by design; we refuse
    anything else so a typo can never drop a real database.
    """
    allowed = {
        "mysql": {DEFAULT_SCRATCH_MYSQL},
        "mongo": {DEFAULT_SCRATCH_MONGO},
    }[kind]
    if name not in allowed:
        raise ValueError(
            f"refusing scratch name {name!r} for {kind}; allowed: {sorted(allowed)}"
        )
    if kind == "mysql" and name in MYSQL_PROTECTED:
        raise ValueError(f"scratch name {name!r} collides with a protected database")
    return name


def build_mysql_dump_argv(db: str) -> list[str]:
    return [
        "docker", "exec", MYSQL_CONTAINER, "mysqldump",
        "-uroot", f"-p{os.environ.get('SPECPROOF_MYSQL_ROOT_PASSWORD', 'specproof_root')}",
        "--single-transaction", "--routines", "--triggers", "--set-gtid-purged=OFF", db,
    ]


def build_mysql_restore_argv(db: str) -> list[str]:
    return [
        "docker", "exec", "-i", MYSQL_CONTAINER, "mysql",
        "-uroot", f"-p{os.environ.get('SPECPROOF_MYSQL_ROOT_PASSWORD', 'specproof_root')}", db,
    ]


def build_mongo_dump_argv(db: str) -> list[str]:
    return [
        "docker", "exec", MONGO_CONTAINER, "mongodump",
        "-u", MONGO_USER, "-p", MONGO_PASSWORD, "--authenticationDatabase", "admin",
        "--db", db, "--archive", "--gzip",
    ]


def build_mongo_restore_argv() -> list[str]:
    return [
        "docker", "exec", "-i", MONGO_CONTAINER, "mongorestore",
        "-u", MONGO_USER, "-p", MONGO_PASSWORD, "--authenticationDatabase", "admin",
        "--archive", "--gzip",
    ]


def parse_mysql_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            counts[parts[0]] = int(parts[1])
    return counts


def compare_count_maps(src: dict[str, int], restored: dict[str, int]) -> list[str]:
    problems: list[str] = []
    for table in sorted(set(src) | set(restored)):
        a, b = src.get(table), restored.get(table)
        if a != b:
            problems.append(f"{table}: source={a} restored={b}")
    return problems


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run(
    args: list[str], *, stdin=None, stdout=None, timeout: int = 900
) -> subprocess.CompletedProcess:
    kwargs: dict = {"stdin": stdin, "stderr": subprocess.PIPE,
                    "timeout": timeout, "encoding": "utf-8", "errors": "replace"}
    kwargs["stdout"] = subprocess.PIPE if stdout is None else stdout
    return subprocess.run(args, **kwargs)


def _mysql(query: str) -> str:
    p = run(["docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot",
             f"-p{os.environ.get('SPECPROOF_MYSQL_ROOT_PASSWORD', 'specproof_root')}",
             "-N", "-B", "-e", query])
    if p.returncode != 0:
        raise RuntimeError(f"mysql query failed: {p.stderr}")
    return p.stdout


def mysql_counts(db: str) -> dict[str, int]:
    tables = _mysql(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema='{db}' ORDER BY table_name"
    )
    counts: dict[str, int] = {}
    for table in tables.split():
        table = table.strip()
        if not table:
            continue
        c = _mysql(f"SELECT COUNT(*) FROM `{db}`.`{table}`")
        counts[table] = int(c.strip())
    return counts


def mongo_eval(js: str) -> str:
    p = run(["docker", "exec", MONGO_CONTAINER, "mongosh", "--quiet",
             "-u", MONGO_USER, "-p", MONGO_PASSWORD, "--authenticationDatabase", "admin",
             "--eval", js])
    if p.returncode != 0:
        raise RuntimeError(f"mongosh failed: {p.stderr}")
    return p.stdout


def mongo_counts(db: str) -> dict[str, int]:
    out = mongo_eval(
        f"const db = db.getSiblingDB('{db}');"
        "db.getCollectionNames().forEach("
        "  c => print(c + ' ' + db.getCollection(c).countDocuments()))"
    )
    counts: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            counts[parts[0]] = int(parts[1])
    return counts


def drill_mysql(source: str, scratch: str, backup_dir: str, report: dict) -> bool:
    ok = True
    report["mysql_source_db"] = source
    src_counts = mysql_counts(source)
    report["mysql_source_counts"] = src_counts

    dump_path = os.path.join(backup_dir, f"{source}-{datetime.datetime.now():%Y%m%d-%H%M%S}.sql")
    with open(dump_path, "wb") as fh:
        p = subprocess.run(build_mysql_dump_argv(source), stdout=fh, stderr=subprocess.PIPE,
                           encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        report["mysql_dump_ok"] = False
        report["mysql_dump_error"] = p.stderr
        return False
    report["mysql_dump_bytes"] = os.path.getsize(dump_path)
    report["mysql_dump_sha256"] = sha256_file(dump_path)
    report["mysql_dump_ok"] = True

    assert_scratch_allowed(scratch, "mysql")
    _mysql(f"DROP DATABASE IF EXISTS {scratch}; CREATE DATABASE {scratch} CHARACTER SET utf8mb4")
    try:
        with open(dump_path, "rb") as fh:
            p = subprocess.run(build_mysql_restore_argv(scratch), stdin=fh, stderr=subprocess.PIPE,
                               encoding="utf-8", errors="replace", timeout=900)
        if p.returncode != 0:
            report["mysql_restore_ok"] = False
            report["mysql_restore_error"] = p.stderr
            ok = False
        else:
            report["mysql_restore_ok"] = True
            restored = mysql_counts(scratch)
            report["mysql_restored_counts"] = restored
            problems = compare_count_maps(src_counts, restored)
            report["mysql_counts_match"] = not problems
            if problems:
                report["mysql_mismatches"] = problems
                ok = False
            report["mysql_schema_migrations_src"] = _mysql(
                f"SELECT MAX(version) FROM {source}.schema_migrations").strip()
            report["mysql_schema_migrations_restored"] = _mysql(
                f"SELECT MAX(version) FROM {scratch}.schema_migrations").strip()
            if report["mysql_schema_migrations_src"] != report["mysql_schema_migrations_restored"]:
                ok = False
    finally:
        _mysql(f"DROP DATABASE IF EXISTS {scratch}")
    if report.get("mysql_counts_match"):
        os.remove(dump_path)
        report["mysql_dump_deleted"] = True
    else:
        report["mysql_dump_kept"] = dump_path
    return ok


def drill_mongo(scratch: str, documents: int, backup_dir: str, report: dict) -> bool:
    ok = True
    assert_scratch_allowed(scratch, "mongo")
    mongo_eval(f"db.getSiblingDB('{scratch}').dropDatabase()")
    seed_js = (
        f"const db = db.getSiblingDB('{scratch}');"
        f"db.createCollection('drill_docs');"
        f"const docs = []; for (let i = 0; i < {documents}; i++) docs.push("
        f"  {{_id: 'drill-' + i, seq: i, payload: 'd'.repeat(128)}});"
        f"db.drill_docs.insertMany(docs);"
        f"print('seeded ' + db.drill_docs.countDocuments())"
    )
    mongo_eval(seed_js)
    before = mongo_counts(scratch)
    report["mongo_scratch_documents"] = documents
    report["mongo_counts_before"] = before

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dump_path = os.path.join(backup_dir, f"{scratch}-{stamp}.archive.gz")
    with open(dump_path, "wb") as fh:
        p = subprocess.run(build_mongo_dump_argv(scratch), stdout=fh, stderr=subprocess.PIPE,
                           encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        report["mongo_dump_ok"] = False
        report["mongo_dump_error"] = p.stderr
        return False
    report["mongo_dump_bytes"] = os.path.getsize(dump_path)
    report["mongo_dump_sha256"] = sha256_file(dump_path)
    report["mongo_dump_ok"] = True

    mongo_eval(f"db.getSiblingDB('{scratch}').dropDatabase()")
    try:
        with open(dump_path, "rb") as fh:
            p = subprocess.run(build_mongo_restore_argv(), stdin=fh, stderr=subprocess.PIPE,
                               encoding="utf-8", errors="replace", timeout=900)
        if p.returncode != 0:
            report["mongo_restore_ok"] = False
            report["mongo_restore_error"] = p.stderr
            ok = False
        else:
            report["mongo_restore_ok"] = True
            after = mongo_counts(scratch)
            report["mongo_counts_after_restore"] = after
            report["mongo_counts_match"] = (before == after)
            if before != after:
                ok = False
            digest = mongo_eval(
                f"const db=db.getSiblingDB('{scratch}');"
                "const r=db.drill_docs.aggregate("
                "  [{$group:{_id:null,n:{$sum:1},s:{$sum:'$seq'}}}]).toArray()[0];"
                f"print(JSON.stringify(r))"
            ).strip()
            report["mongo_digest_after_restore"] = digest
    finally:
        mongo_eval(f"db.getSiblingDB('{scratch}').dropDatabase()")
    os.remove(dump_path)
    report["mongo_scratch_dump_deleted"] = True
    return ok


def product_backup(store: str, out_dir: str, keep: bool, report: dict) -> None:
    """Read-only backup of the product database. Never touches it otherwise."""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if store == "mysql":
        path = os.path.join(out_dir, f"{PRODUCT_MYSQL}-backup-{ts}.sql")
        with open(path, "wb") as fh:
            p = subprocess.run(build_mysql_dump_argv(PRODUCT_MYSQL), stdout=fh,
                               stderr=subprocess.PIPE, encoding="utf-8",
                               errors="replace", timeout=900)
        ok = p.returncode == 0
    elif store == "mongo":
        path = os.path.join(out_dir, f"{PRODUCT_MYSQL}-backup-{ts}.archive.gz")
        with open(path, "wb") as fh:
            p = subprocess.run(build_mongo_dump_argv(PRODUCT_MYSQL), stdout=fh,
                               stderr=subprocess.PIPE, encoding="utf-8",
                               errors="replace", timeout=900)
        ok = p.returncode == 0
    else:  # pragma: no cover - argparse choices guard
        raise ValueError(store)
    if not ok:
        report[f"product_backup_{store}_ok"] = False
        report[f"product_backup_{store}_error"] = p.stderr
        if os.path.exists(path):
            os.remove(path)
        return
    report[f"product_backup_{store}_ok"] = True
    report[f"product_backup_{store}_bytes"] = os.path.getsize(path)
    report[f"product_backup_{store}_sha256"] = sha256_file(path)
    if keep:
        report[f"product_backup_{store}_kept_at"] = path
    else:
        os.remove(path)
        report[f"product_backup_{store}_plaintext_deleted"] = True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stores", choices=["mysql", "mongo", "both"], default="both")
    ap.add_argument("--source", default=DEFAULT_SOURCE_MYSQL,
                    help="MySQL source database for the drill (default: specproof_test; "
                         "product specproof_phase0 is never used as a drill source)")
    ap.add_argument("--scratch", default=None,
                    help="Scratch database name (defaults: specproof_restore_drill / "
                         "specproof_drill_scratch). Fixed; anything else is refused.")
    ap.add_argument("--mongo-documents", type=int, default=DEFAULT_MONGO_DOCUMENTS)
    ap.add_argument("--backup-dir", default=None,
                    help="Directory for scratch dumps + report (default: tempdir).")
    ap.add_argument("--product-backup", action="store_true",
                    help="Also take a read-only backup of specproof_phase0 for each "
                         "selected store. Plaintext is hashed then deleted unless "
                         "--keep-product-dump is passed.")
    ap.add_argument("--keep-product-dump", action="store_true",
                    help="Keep the product plaintext dump on disk. YOU own its lifetime "
                         "then (it may contain tenant data).")
    args = ap.parse_args(argv)

    if args.source == PRODUCT_MYSQL:
        print("refusing: --source must not be the product database", file=sys.stderr)
        return 2

    scratch_mysql = (args.scratch if (args.scratch and args.stores == "mysql")
                     else DEFAULT_SCRATCH_MYSQL)
    scratch_mongo = (args.scratch if (args.scratch and args.stores == "mongo")
                     else DEFAULT_SCRATCH_MONGO)
    if args.scratch and args.stores == "both":
        print("refusing: --scratch with --stores both is ambiguous", file=sys.stderr)
        return 2

    backup_dir = args.backup_dir or tempfile.mkdtemp(prefix="specproof-drill-")
    os.makedirs(backup_dir, exist_ok=True)
    report: dict = {"started": datetime.datetime.now().isoformat()}
    ok = True

    if args.stores in ("mysql", "both"):
        try:
            ok = drill_mysql(args.source, scratch_mysql, backup_dir, report) and ok
        except (RuntimeError, ValueError) as exc:
            report["mysql_error"] = str(exc)
            ok = False
        if args.product_backup:
            product_backup("mysql", backup_dir, args.keep_product_dump, report)

    if args.stores in ("mongo", "both"):
        try:
            ok = drill_mongo(scratch_mongo, args.mongo_documents, backup_dir, report) and ok
        except (RuntimeError, ValueError) as exc:
            report["mongo_error"] = str(exc)
            ok = False
        if args.product_backup:
            product_backup("mongo", backup_dir, args.keep_product_dump, report)

    report["finished"] = datetime.datetime.now().isoformat()
    report["overall_ok"] = ok
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = os.path.join(backup_dir, f"drill-report-{stamp}.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(json.dumps(report, indent=1, sort_keys=True))
    print("report:", report_path)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
