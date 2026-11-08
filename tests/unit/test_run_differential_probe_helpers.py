"""Direct behavioral tests for the small pure helpers on the
run_differential probe evidence path.

These helpers decide what the reader of a NON_REPRODUCIBLE record can see
(the first Maven [ERROR] line, the tail of a side's output) and what a probe
digest attests (flags only, never raw timestamps). None of them was
previously exercised directly; they were only reachable through a full
pipeline run.
"""

from agent.nodes.run_differential import (
    _first_maven_error_line,
    _probe_digest_payload,
    _probe_output_tail,
    _test_class_from_path,
)

# -- _test_class_from_path ---------------------------------------------------


def test_test_class_from_path_strips_directory_and_java_suffix() -> None:
    assert _test_class_from_path(
        "some/where/SpecProofGeneratedTest.java"
    ) == "SpecProofGeneratedTest"


def test_test_class_from_path_handles_bare_name() -> None:
    assert _test_class_from_path("SpecProofGeneratedTest.java") == (
        "SpecProofGeneratedTest"
    )


def test_test_class_from_path_empty_input() -> None:
    assert _test_class_from_path("") == ""


def test_test_class_from_path_dot_java_only() -> None:
    assert _test_class_from_path(".java") == ""


# -- _first_maven_error_line ---------------------------------------------------


def test_first_maven_error_line_finds_error_in_stdout() -> None:
    result = {"stdout": "[INFO] build\n[ERROR] Could not resolve dependencies\n[INFO] done",
              "stderr": ""}
    assert _first_maven_error_line(result) == "[ERROR] Could not resolve dependencies"


def test_first_maven_error_line_finds_error_in_stderr() -> None:
    result = {"stdout": "", "stderr": "[ERROR] offline mode failed"}
    assert _first_maven_error_line(result) == "[ERROR] offline mode failed"


def test_first_maven_error_line_returns_empty_when_no_error() -> None:
    result = {"stdout": "[INFO] BUILD SUCCESS", "stderr": ""}
    assert _first_maven_error_line(result) == ""


def test_first_maven_error_line_prefers_the_first_result() -> None:
    base = {"stdout": "[ERROR] base failure", "stderr": ""}
    head = {"stdout": "[ERROR] head failure", "stderr": ""}
    assert _first_maven_error_line(base, head) == "[ERROR] base failure"
    assert _first_maven_error_line(head, base) == "[ERROR] head failure"


def test_first_maven_error_line_caps_at_300_chars() -> None:
    result = {"stdout": "[ERROR] " + "x" * 400, "stderr": ""}
    line = _first_maven_error_line(result)
    assert len(line) == 300


# -- _probe_digest_payload ------------------------------------------------------


def test_probe_digest_payload_both_sides_carry_flags() -> None:
    base_artifact = {
        "publish_count": 1,
        "outcome": "accepted",
        "payloads": [{"timestamp": 123}, {"timestamp": 124}],
    }
    head_artifact = {
        "publish_count": 2,
        "outcome": "rejected",
        "payloads": [{"timestamp": None}, {"timestamp": 127}],
    }
    payload = _probe_digest_payload("REGRESSION", base_artifact, head_artifact)
    assert payload["verdict"] == "REGRESSION"
    assert payload["base"] == {
        "publish_count": 1,
        "outcome": "accepted",
        "payload_count": 2,
        "all_timestamps_non_null": True,
    }
    assert payload["head"] == {
        "publish_count": 2,
        "outcome": "rejected",
        "payload_count": 2,
        "all_timestamps_non_null": False,
    }


def test_probe_digest_payload_none_artifact_side_stays_none() -> None:
    artifact = {"publish_count": 1, "outcome": "accepted", "payloads": []}
    assert _probe_digest_payload("COMPLIANT", None, artifact)["base"] is None
    assert _probe_digest_payload("COMPLIANT", artifact, None)["head"] is None


def test_probe_digest_payload_empty_payloads_flag_false() -> None:
    artifact = {"publish_count": 0, "outcome": "accepted", "payloads": []}
    payload = _probe_digest_payload("COMPLIANT", artifact, artifact)
    assert payload["base"]["all_timestamps_non_null"] is False


def test_probe_digest_payload_never_leaks_raw_timestamps() -> None:
    artifact = {
        "publish_count": 1,
        "outcome": "accepted",
        "payloads": [{"timestamp": 999, "token": "secret"}],
    }
    payload = _probe_digest_payload("COMPLIANT", artifact, artifact)
    for side in (payload["base"], payload["head"]):
        assert set(side) == {
            "publish_count",
            "outcome",
            "payload_count",
            "all_timestamps_non_null",
        }
        assert "999" not in str(side)
        assert "secret" not in str(side)


# -- _probe_output_tail -----------------------------------------------------------


def test_probe_output_tail_concatenates_stdout_and_stderr() -> None:
    run = {"stdout": "out", "stderr": "err"}
    assert _probe_output_tail(run) == "outerr"


def test_probe_output_tail_empty_run_returns_empty_string() -> None:
    assert _probe_output_tail({}) == ""
    assert _probe_output_tail({"stdout": "", "stderr": ""}) == ""


def test_probe_output_tail_caps_with_ellipsis_prefix() -> None:
    run = {"stdout": "y" * 2500, "stderr": ""}
    tail = _probe_output_tail(run)
    assert tail.startswith("...")
    assert len(tail) == 2003
    assert tail[3:] == "y" * 2000


def test_probe_output_tail_handles_non_string_values() -> None:
    run = {"stdout": None, "stderr": None}
    assert _probe_output_tail(run) == ""
