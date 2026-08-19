"""Unit tests for providers.toolcheck.ToolCallSelfCheck — no network, no Docker.

The model round-trip is an injected callable (EnvelopeProducer): tests feed
it canned envelopes and inspect the ONE retry instruction plus the
counters. Registry schemas are built inline; from_registry is exercised
with a duck-typed fake mirroring craft.tools.ToolRegistry/ToolSpec/Param.
"""

from types import SimpleNamespace

import pytest

from providers.toolcheck import (
    CODE_INVALID_ARGUMENTS,
    CODE_UNKNOWN_TOOL,
    CODE_VERSION_MISMATCH,
    ParamSchema,
    ToolCallSelfCheck,
    ToolSchema,
    retry_instruction,
    validate_envelope,
)


def _registry() -> dict[str, ToolSchema]:
    return {
        "read_file": ToolSchema(
            name="read_file",
            version=1,
            params=(
                ParamSchema("path", "str", required=True, max_len=512),
                ParamSchema("offset", "int", min_value=1, max_value=1_000_000),
                ParamSchema("limit", "int", min_value=1, max_value=2000),
            ),
        ),
        "run_test": ToolSchema(
            name="run_test",
            version=1,
            params=(
                ParamSchema("command", "list[str]", required=True, max_len=64),
                ParamSchema("timeout", "int", min_value=1, max_value=3600),
            ),
        ),
    }


def _valid_read_file() -> dict[str, object]:
    return {"action": "read_file", "version": 1, "params": {"path": "a.py"}}


class TestValidEnvelope:
    def test_valid_envelope_passes(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        instructions: list[str | None] = []

        def produce(instruction: str | None) -> object:
            instructions.append(instruction)
            return _valid_read_file()

        outcome = checker.check_with_retry(produce)
        assert outcome.status == "valid"
        assert outcome.code == ""
        assert outcome.tool == "read_file"
        assert outcome.version == 1
        assert instructions == [None]  # no retry instruction ever emitted
        assert checker.metrics() == {
            "attempts": 1,
            "valid": 1,
            "retried": 0,
            "success": 1,
            "give_ups": 0,
            "tool_call_success_rate": 1.0,
        }

    def test_absent_version_stamps_registered_version(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        outcome = checker.check({"action": "read_file", "params": {"path": "a.py"}})
        assert outcome.status == "valid"
        assert outcome.version == 1

    def test_optional_params_absent_is_valid(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        outcome = checker.check(
            {"action": "read_file", "version": 1, "params": {"path": "a.py"}}
        )
        assert outcome.status == "valid"

    def test_unknown_top_level_keys_are_ignored(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        envelope = {
            "action": "run_test",
            "version": 1,
            "params": {"command": ["pytest"], "timeout": 60},
            "commentary": "ignore me",
        }
        assert checker.check(envelope).status == "valid"


class TestUnknownTool:
    def test_unknown_tool_emits_one_retry_then_gives_up(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        bad = {"action": "rm_rf", "version": 1, "params": {}}
        instructions: list[str | None] = []

        def produce(instruction: str | None) -> object:
            instructions.append(instruction)
            return bad

        outcome = checker.check_with_retry(produce)
        assert outcome.status == "give_up"
        assert outcome.code == CODE_UNKNOWN_TOOL
        assert outcome.tool == "rm_rf"
        assert instructions[0] is None
        assert instructions[1] is not None
        assert "[UNKNOWN_TOOL]" in instructions[1]
        assert "rm_rf" in instructions[1]
        assert "JSON Action Envelope" in instructions[1]
        assert checker.metrics() == {
            "attempts": 2,
            "valid": 0,
            "retried": 1,
            "success": 0,
            "give_ups": 1,
            "tool_call_success_rate": 0.0,
        }
        # give-up verdict matches the pure validation of the same envelope
        pure = validate_envelope(_registry(), bad)
        assert pure.code == outcome.code
        assert pure.message == outcome.message

    def test_missing_action_is_unknown_tool_retry(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        outcome = checker.check({"version": 1, "params": {}})
        assert outcome.status == "retry"
        assert outcome.code == CODE_UNKNOWN_TOOL

    def test_valid_call_after_a_retry_resets_the_state(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        assert checker.check({"action": "nope", "params": {}}).status == "retry"
        assert checker.check(_valid_read_file()).status == "valid"
        # the retry armed by the first call was consumed by the valid call:
        assert checker.check({"action": "nope", "params": {}}).status == "retry"
        assert checker.give_ups == 0


class TestVersionMismatch:
    def test_version_mismatch_retry_then_corrected_passes(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        calls = 0
        instructions: list[str | None] = []

        def produce(instruction: str | None) -> object:
            nonlocal calls
            calls += 1
            instructions.append(instruction)
            if calls == 1:
                return {"action": "read_file", "version": 2, "params": {"path": "a.py"}}
            return _valid_read_file()

        outcome = checker.check_with_retry(produce)
        assert outcome.status == "valid"
        assert outcome.tool == "read_file"
        assert instructions[0] is None
        assert instructions[1] is not None
        assert "[TOOL_VERSION_MISMATCH]" in instructions[1]
        assert checker.metrics()["attempts"] == 2
        assert checker.metrics()["valid"] == 1
        assert checker.metrics()["retried"] == 1
        assert checker.metrics()["give_ups"] == 0
        assert checker.metrics()["tool_call_success_rate"] == 0.5

    def test_version_mismatch_twice_gives_up_with_code(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        bad = {"action": "read_file", "version": 2, "params": {"path": "a.py"}}

        def produce(_instruction: str | None) -> object:
            return bad

        outcome = checker.check_with_retry(produce)
        assert outcome.status == "give_up"
        assert outcome.code == CODE_VERSION_MISMATCH
        assert checker.metrics()["give_ups"] == 1

    def test_non_integer_version_is_a_version_mismatch(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        outcome = checker.check(
            {"action": "read_file", "version": "1", "params": {"path": "a.py"}}
        )
        assert outcome.status == "retry"
        assert outcome.code == CODE_VERSION_MISMATCH


class TestArgumentValidation:
    def test_argument_out_of_range_retry_then_gives_up(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        bad = {"action": "read_file", "version": 1, "params": {"path": "a.py", "limit": 99999}}
        instructions: list[str | None] = []

        def produce(instruction: str | None) -> object:
            instructions.append(instruction)
            return bad

        outcome = checker.check_with_retry(produce)
        assert outcome.status == "give_up"
        assert outcome.code == CODE_INVALID_ARGUMENTS
        assert "[INVALID_ARGUMENTS]" in instructions[1]
        assert "limit" in instructions[1]

    def test_wrong_argument_type_is_rejected(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        bad = {
            "action": "run_test",
            "version": 1,
            "params": {"command": "pytest", "timeout": 60},
        }
        outcome = checker.check(bad)
        assert outcome.status == "retry"
        assert outcome.code == CODE_INVALID_ARGUMENTS

    def test_bool_is_not_an_int(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        bad = {
            "action": "run_test",
            "version": 1,
            "params": {"command": ["pytest"], "timeout": True},
        }
        outcome = checker.check(bad)
        assert outcome.status == "retry"
        assert outcome.code == CODE_INVALID_ARGUMENTS

    def test_unknown_argument_key_is_rejected(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        bad = {
            "action": "read_file",
            "version": 1,
            "params": {"path": "a.py", "sudo": True},
        }
        outcome = checker.check(bad)
        assert outcome.status == "retry"
        assert outcome.code == CODE_INVALID_ARGUMENTS

    def test_missing_required_param_is_rejected(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        outcome = checker.check(
            {"action": "read_file", "version": 1, "params": {"offset": 1}}
        )
        assert outcome.status == "retry"
        assert outcome.code == CODE_INVALID_ARGUMENTS

    def test_reason_key_is_tolerated(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        envelope = {
            "action": "read_file",
            "version": 1,
            "params": {"path": "a.py", "reason": "looking for the bug"},
        }
        assert checker.check(envelope).status == "valid"


class TestMalformedEnvelopes:
    def test_non_dict_envelope_retry_then_gives_up(self) -> None:
        checker = ToolCallSelfCheck(_registry())

        def produce(_instruction: str | None) -> object:
            return "definitely not json"

        outcome = checker.check_with_retry(produce)
        assert outcome.status == "give_up"
        assert outcome.code == CODE_INVALID_ARGUMENTS

    def test_params_not_a_dict_is_rejected(self) -> None:
        checker = ToolCallSelfCheck(_registry())
        outcome = checker.check({"action": "read_file", "version": 1, "params": "a.py"})
        assert outcome.status == "retry"
        assert outcome.code == CODE_INVALID_ARGUMENTS


class TestRegistryAdapter:
    def test_from_registry_duck_types_tool_registry(self) -> None:
        class _FakeRegistry:
            def specs(self) -> dict[str, object]:
                path = SimpleNamespace(
                    name="path",
                    kind="str",
                    required=True,
                    max_len=512,
                    min_value=None,
                    max_value=None,
                )
                spec = SimpleNamespace(name="read_file", version=1, params=(path,))
                return {"read_file": spec}

        checker = ToolCallSelfCheck.from_registry(_FakeRegistry())
        assert checker.check({"action": "read_file", "params": {"path": "x"}}).status == "valid"
        bad = checker.check({"action": "read_file", "params": {}})
        assert bad.status == "retry"
        assert bad.code == CODE_INVALID_ARGUMENTS

    def test_from_registry_accepts_plain_mapping(self) -> None:
        checker = ToolCallSelfCheck.from_registry(_registry())
        assert checker.check(_valid_read_file()).status == "valid"

    def test_from_registry_rejects_objects_without_specs(self) -> None:
        with pytest.raises(TypeError):
            ToolCallSelfCheck.from_registry(object())


class TestRetryInstruction:
    def test_instruction_is_deterministic_and_stable(self) -> None:
        outcome = validate_envelope(_registry(), {"action": "nope", "params": {}})
        first = retry_instruction(outcome)
        second = retry_instruction(outcome)
        assert first == second
        assert "TOOL CALL SELF-CHECK" in first
        assert "REJECTED and NOT executed" in first
        assert "JSON Action Envelope" in first
        assert "No markdown fences" in first


def test_metrics_success_rate_across_separate_calls() -> None:
    checker = ToolCallSelfCheck(_registry())
    assert checker.check(_valid_read_file()).status == "valid"
    assert checker.check({"action": "nope", "params": {}}).status == "retry"
    metrics = checker.metrics()
    assert metrics["attempts"] == 2
    assert metrics["valid"] == 1
    assert metrics["retried"] == 1
    assert metrics["tool_call_success_rate"] == 0.5


def test_last_outcome_tracks_most_recent_check() -> None:
    checker = ToolCallSelfCheck(_registry())
    outcome = checker.check(_valid_read_file())
    assert checker.last_outcome is outcome
