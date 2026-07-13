"""Unit tests for P1.1 MySQL job state machine."""

import pytest

from storage.mysql import (
    _VALID_TRANSITIONS,
    InvalidStateTransitionError,
    JobNotFoundError,
    MySQLStore,
    OptimisticLockFailureError,
)


class TestStateMachineConstants:
    def test_all_10_statuses_exist(self) -> None:
        expected = {
            "CREATED", "QUEUED", "PREPARING", "RUNNING",
            "WAITING_FOR_PROVIDER", "WAITING_FOR_APPROVAL",
            "SUCCEEDED", "FAILED", "CANCELLED", "STALE",
        }
        assert set(_VALID_TRANSITIONS.keys()) == expected

    def test_terminal_statuses_have_no_exits(self) -> None:
        for status in ("SUCCEEDED", "FAILED", "CANCELLED", "STALE"):
            assert _VALID_TRANSITIONS[status] == set()

    def test_created_can_only_go_to_queued_or_cancelled(self) -> None:
        assert _VALID_TRANSITIONS["CREATED"] == {"QUEUED", "CANCELLED"}

    def test_running_has_most_transitions(self) -> None:
        assert len(_VALID_TRANSITIONS["RUNNING"]) >= 5


class TestValidTransitions:
    @pytest.mark.parametrize("from_s,to_s", [
        ("CREATED", "QUEUED"),
        ("CREATED", "CANCELLED"),
        ("QUEUED", "PREPARING"),
        ("QUEUED", "STALE"),
        ("PREPARING", "RUNNING"),
        ("PREPARING", "FAILED"),
        ("RUNNING", "WAITING_FOR_PROVIDER"),
        ("RUNNING", "WAITING_FOR_APPROVAL"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED"),
        ("RUNNING", "STALE"),
        ("WAITING_FOR_PROVIDER", "RUNNING"),
        ("WAITING_FOR_APPROVAL", "RUNNING"),
        ("WAITING_FOR_APPROVAL", "SUCCEEDED"),
        ("QUEUED", "CANCELLED"),
        ("PREPARING", "CANCELLED"),
        ("RUNNING", "CANCELLED"),
        ("WAITING_FOR_PROVIDER", "CANCELLED"),
        ("WAITING_FOR_APPROVAL", "CANCELLED"),
    ])
    def test_valid_transitions(self, from_s: str, to_s: str) -> None:
        assert MySQLStore.is_valid_transition(from_s, to_s)


class TestInvalidTransitions:
    @pytest.mark.parametrize("from_s,to_s", [
        ("CREATED", "RUNNING"),           # skip QUEUED
        ("CREATED", "SUCCEEDED"),         # impossible
        ("QUEUED", "SUCCEEDED"),          # skip all execution
        ("SUCCEEDED", "RUNNING"),         # terminal
        ("CANCELLED", "QUEUED"),          # terminal
        ("STALE", "RUNNING"),             # terminal
        ("RUNNING", "CREATED"),           # backward
        ("PREPARING", "QUEUED"),          # backward
        ("WAITING_FOR_PROVIDER", "QUEUED"),  # wrong direction
    ])
    def test_invalid_transitions(self, from_s: str, to_s: str) -> None:
        assert not MySQLStore.is_valid_transition(from_s, to_s)


class TestTerminalDetection:
    @pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED", "CANCELLED", "STALE"])
    def test_terminal(self, status: str) -> None:
        assert MySQLStore.is_terminal(status)

    @pytest.mark.parametrize("status", [
        "CREATED", "QUEUED", "PREPARING", "RUNNING",
        "WAITING_FOR_PROVIDER", "WAITING_FOR_APPROVAL",
    ])
    def test_non_terminal(self, status: str) -> None:
        assert not MySQLStore.is_terminal(status)


class TestExceptionHierarchy:
    def test_invalid_transition_is_exception(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            raise InvalidStateTransitionError("test")

    def test_job_not_found_is_exception(self) -> None:
        with pytest.raises(JobNotFoundError):
            raise JobNotFoundError("test")

    def test_optimistic_lock_is_exception(self) -> None:
        with pytest.raises(OptimisticLockFailureError):
            raise OptimisticLockFailureError("test")
