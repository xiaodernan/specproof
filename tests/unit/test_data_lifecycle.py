"""Unit tests for the data lifecycle CLI (export / delete / backup probe)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ops.data_lifecycle as lifecycle


class FakeMySQL:
    def __init__(self) -> None:
        self.deleted: dict[str, int] = {}

    def connection(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def cursor(self):
        return self

    def execute(self, sql, params=()) -> None:
        self._last_sql = sql

    def fetchone(self):
        return {"id": "j1", "status": "BLOCKED"}

    def fetchall(self):
        return [{"id": "f1"}]

    rowcount = 2

    def delete_job_records(self, job_id):
        self.deleted = {"findings": 2, "contracts": 1, "jobs": 1}
        return self.deleted


class FakeMongo:
    def get_differential_run(self, job_id):
        return {"job_id": job_id, "verdict": "REGRESSION"}

    def get_evidence_packs_for_job(self, job_id):
        return [{"job_id": job_id, "contract_id": "AUTH-01"}]

    def delete_job_artifacts(self, job_id):
        return {"differential_runs": 1, "evidence_packs": 1}


class FakeES:
    def delete_projection(self, job_id=None, tenant_id=None):
        return 3


class FakeMinIO:
    def list_job_objects(self, job_id):
        return ["capsule-1.zip", "report.html"]


@pytest.fixture()
def fake_stores(monkeypatch):
    monkeypatch.setattr("storage.mysql.MySQLStore", FakeMySQL)
    monkeypatch.setattr("storage.mongodb.MongoDBStore", FakeMongo)
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", FakeES)
    monkeypatch.setattr("storage.minio.MinIOClient", FakeMinIO)


def test_export_job_writes_json(fake_stores, tmp_path: Path) -> None:
    result = lifecycle.export_job("j1", tmp_path)
    assert result["degraded"] == []
    assert result["mysql"]["job"]["id"] == "j1"
    export_file = tmp_path / "j1" / "export.json"
    assert export_file.is_file()
    payload = json.loads(export_file.read_text(encoding="utf-8"))
    assert payload["mongo"]["differential_runs"]["verdict"] == "REGRESSION"


def test_export_job_mysql_down_degrades(monkeypatch, tmp_path: Path) -> None:
    class DownMySQL:
        def connection(self):
            raise ConnectionError("down")

    monkeypatch.setattr("storage.mysql.MySQLStore", DownMySQL)
    monkeypatch.setattr("storage.mongodb.MongoDBStore", FakeMongo)
    result = lifecycle.export_job("j1", tmp_path)
    assert "mysql unavailable" in result["degraded"][0]
    assert result["mysql"] is None
    assert result["mongo"] is not None


def test_delete_job_documented_order(fake_stores) -> None:
    report = lifecycle.delete_job("j1")
    assert report["steps"]["es_projection"]["ok"] is True
    assert report["steps"]["es_projection"]["deleted"] == 3
    assert report["steps"]["mongo_artifacts"]["differential_runs"] == 1
    assert report["steps"]["mysql_records"]["jobs"] == 1
    minio_step = report["steps"]["minio_listed_not_deleted"]
    assert minio_step["ok"] is True
    assert minio_step["objects"] == ["capsule-1.zip", "report.html"]
    assert "never auto-deleted" in minio_step["note"]


def test_delete_job_step_failure_reported(fake_stores, monkeypatch) -> None:
    class DownES:
        def delete_projection(self, job_id=None, tenant_id=None):
            raise ConnectionError("es down")

    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", DownES)
    report = lifecycle.delete_job("j1")
    assert report["steps"]["es_projection"]["ok"] is False
    assert "es down" in report["steps"]["es_projection"]["error"]
    # Later steps still run — deletion is best-effort per step.
    assert report["steps"]["mysql_records"]["ok"] is True


def test_backup_probe_schema() -> None:
    probe = lifecycle.backup_probe()
    assert isinstance(probe["mysqldump"], bool)
    assert isinstance(probe["mongodump"], bool)
    assert isinstance(probe["docker"], bool)
    assert "DRILLS 4" in probe["note"]


def test_main_delete_requires_confirm(fake_stores, capsys) -> None:
    code = lifecycle.main(["delete-job", "j1"])
    assert code == 2
    assert "--confirm" in capsys.readouterr().out
