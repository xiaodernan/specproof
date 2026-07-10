"""Shared test fixtures and configuration."""

import os
import uuid
from collections.abc import Generator

import pytest


@pytest.fixture
def temp_job_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
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

    yield

    for key, val in saved.items():
        if val is not None:
            os.environ[key] = val
