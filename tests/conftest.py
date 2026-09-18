"""Shared test fixtures and configuration."""

import os
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_job_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def clean_env(tmp_path: Path) -> Generator[None, None, None]:
    """Ensure no real API keys leak into test environment."""
    sensitive = [
        "LLM_API_KEY",
        "MYSQL_PASSWORD",
        "MONGODB_PASSWORD",
        "ES_PASSWORD",
        "REDIS_PASSWORD",
        "RABBITMQ_PASSWORD",
        "MINIO_ROOT_PASSWORD",
    ]
    saved = {}
    for key in sensitive:
        saved[key] = os.environ.pop(key, None)
    # Never load private local model credentials during unit tests.
    saved["SPECPROOF_MODEL_CONFIG"] = os.environ.get("SPECPROOF_MODEL_CONFIG")
    os.environ["SPECPROOF_MODEL_CONFIG"] = str(tmp_path / "unconfigured-model.json")
    # §A task 7: keep the object metadata store hermetic in tests — the
    # default backend must never touch ~/.specproof/*.sqlite3 here.
    saved["SPECPROOF_OBJECT_METADATA_BACKEND"] = os.environ.pop(
        "SPECPROOF_OBJECT_METADATA_BACKEND", None
    )
    os.environ["SPECPROOF_OBJECT_METADATA_BACKEND"] = "memory"

    yield

    for key, val in saved.items():
        if val is not None:
            os.environ[key] = val
        else:
            os.environ.pop(key, None)
