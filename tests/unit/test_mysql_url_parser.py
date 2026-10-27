"""#484 — the one MySQL URL parser, pinned directly.

Four stores — ``agent_jobs``, ``billing``, ``identity``, ``object_metadata`` —
each carried a byte-identical copy of this parser. It is now a single public
function, so its branches get direct tests instead of being covered only
incidentally by whichever store a test happened to exercise.

Connection-string parsing is security-adjacent: getting the host, the port or
the database wrong connects somewhere else, and a percent-decoded password
that is not decoded fails to authenticate for a reason nobody can see.
"""
from __future__ import annotations

import pytest
from pymysql.cursors import DictCursor

from storage.mysql_url import parse_mysql_url


def test_a_plain_mysql_url_yields_connection_kwargs() -> None:
    parsed = parse_mysql_url("mysql://u:p@db.internal/db")
    assert parsed["host"] == "db.internal"
    assert parsed["user"] == "u"
    assert parsed["password"] == "p"
    assert parsed["database"] == "db"


def test_the_sqlalchemy_scheme_is_accepted() -> None:
    # The deployment files spell it mysql+pymysql://.
    assert parse_mysql_url("mysql+pymysql://u:p@h/db")["host"] == "h"


def test_a_missing_port_means_3306() -> None:
    assert parse_mysql_url("mysql://h/db")["port"] == 3306


def test_an_explicit_port_wins() -> None:
    assert parse_mysql_url("mysql://h:3307/db")["port"] == 3307


def test_a_missing_path_means_the_default_database() -> None:
    assert parse_mysql_url("mysql://h")["database"] == "specproof"
    assert parse_mysql_url("mysql://h/")["database"] == "specproof"


def test_percent_encoded_credentials_are_decoded() -> None:
    # A password with '@' and ':' in it must survive the URL.
    parsed = parse_mysql_url("mysql://u:p%40ss%3Aword@h/db")
    assert parsed["password"] == "p@ss:word"
    assert parsed["user"] == "u"


def test_missing_credentials_become_empty_strings() -> None:
    parsed = parse_mysql_url("mysql://h/db")
    assert parsed["user"] == ""
    assert parsed["password"] == ""


def test_a_non_mysql_scheme_is_refused_with_the_scheme_named() -> None:
    with pytest.raises(ValueError, match="postgres"):
        parse_mysql_url("postgres://h/db")


def test_a_url_without_a_host_is_refused() -> None:
    with pytest.raises(ValueError, match="host"):
        parse_mysql_url("mysql:///db")


def test_a_malformed_port_is_refused() -> None:
    # urllib raises when the port is not an integer; the parser must not
    # swallow it and connect to a default the operator never asked for.
    with pytest.raises(ValueError, match="Port"):
        parse_mysql_url("mysql://h:abc/db")


def test_the_fixed_connection_options_are_the_documented_ones() -> None:
    parsed = parse_mysql_url("mysql://h/db")
    assert parsed["charset"] == "utf8mb4"
    assert parsed["cursorclass"] is DictCursor
    assert parsed["autocommit"] is False
