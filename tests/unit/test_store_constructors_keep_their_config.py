"""Six stores share one constructor shape; these are the invariants that shape relies on.

Every backend store is written as::

    def __init__(self, config: XConfig | None = None) -> None:
        self.config = config or XConfig.from_env()

#495's queue said "if the three `__init__` copies are ever touched, design a base
class first" — and the answer, after looking at all six, is **no base class**: the
shared part is two lines, and a base would couple six unrelated stores behind a
generic config protocol for no behavioural gain. What is worth doing instead is
pinning the three things that make the two lines correct, because each of them
can be broken silently:

1. an injected config must be used **as given** (not replaced by a fresh env
   read) — that is what lets tests and callers pin a host without touching env;
2. every config class must be **truthy**, because `config or from_env()` silently
   discards a falsy one — a `__bool__` / `__len__` added later would turn an
   explicit config into "no config" with no error anywhere;
3. `from_env()` must run **per instance**, not once at import — otherwise an
   operator (or a test) that sets the env after import is silently ignored.
"""

from __future__ import annotations

from typing import Any

import pytest

from storage.elasticsearch import ElasticsearchConfig, ElasticsearchStore
from storage.minio import MinIOClient, MinIOConfig
from storage.mongodb import MongoDBConfig, MongoDBStore
from storage.mysql import MySQLConfig, MySQLStore
from storage.rabbitmq import RabbitMQClient, RabbitMQConfig
from storage.redis import RedisConfig, RedisStore

# (id, store, config, the env var that config reads its host from)
_PAIRS: list[tuple[str, Any, Any, str]] = [
    ("elasticsearch", ElasticsearchStore, ElasticsearchConfig, "ES_HOST"),
    ("minio", MinIOClient, MinIOConfig, "MINIO_HOST"),
    ("mongodb", MongoDBStore, MongoDBConfig, "MONGODB_HOST"),
    ("mysql", MySQLStore, MySQLConfig, "MYSQL_HOST"),
    ("rabbitmq", RabbitMQClient, RabbitMQConfig, "RABBITMQ_HOST"),
    ("redis", RedisStore, RedisConfig, "REDIS_HOST"),
]


@pytest.mark.parametrize(
    ("name", "store_cls", "config_cls", "host_var"), _PAIRS, ids=[p[0] for p in _PAIRS]
)
def test_an_injected_config_is_used_as_given(
    name: str, store_cls: Any, config_cls: Any, host_var: str,
) -> None:
    config = config_cls()

    store = store_cls(config)

    assert store.config is config, (
        f"{name}: the store replaced the config it was handed — callers can no "
        "longer pin a host without going through the environment"
    )


@pytest.mark.parametrize(
    ("name", "store_cls", "config_cls", "host_var"), _PAIRS, ids=[p[0] for p in _PAIRS]
)
def test_a_config_is_truthy_so_the_or_fallback_cannot_eat_it(
    name: str, store_cls: Any, config_cls: Any, host_var: str,
) -> None:
    """`config or X.from_env()` is only safe while every config is truthy."""
    config = config_cls()

    assert bool(config), (
        f"{name}: {config_cls.__name__} is falsy, so `config or from_env()` "
        "silently replaces an explicitly injected config"
    )


@pytest.mark.parametrize(
    ("name", "store_cls", "config_cls", "host_var"), _PAIRS, ids=[p[0] for p in _PAIRS]
)
def test_each_instance_reads_the_environment_again(
    name: str, store_cls: Any, config_cls: Any, host_var: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A module-level `from_env()` would freeze the environment at import time."""
    monkeypatch.setenv(host_var, "first.invalid")
    first = store_cls().config

    monkeypatch.setenv(host_var, "second.invalid")
    second = store_cls().config

    assert second is not first, "each construction must build its own config object"
    assert first.host == "first.invalid"
    assert second.host == "second.invalid", (
        f"{name}: the second construction still saw {first.host!r} — from_env() "
        "looks cached at import time"
    )


def test_the_mysql_store_picks_up_a_late_environment_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The concrete case an operator hits: set MYSQL_HOST after import, then build."""
    monkeypatch.setenv("MYSQL_HOST", "first.invalid")
    assert MySQLStore().config.host == "first.invalid"

    monkeypatch.setenv("MYSQL_HOST", "second.invalid")
    assert MySQLStore().config.host == "second.invalid", (
        "a cached from_env() would still answer first.invalid"
    )
