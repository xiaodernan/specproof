"""The publish facts a test reported about itself (#366).

The broker side of a publish cannot be observed from outside the test's
JVM (#354). What the pipeline CAN read is the test's own report — the
line the generated test prints with the routing key and the count it
asserted.

These tests pin the reading of that line, and the discipline around its
absence: "the test said nothing" is not "the test observed no publish".
"""

from __future__ import annotations

from experiments.collectors import compare_publish_observations
from experiments.mq_report import parse_mq_observations

REPORT = (
    "SPECPROOF_MQ routing_key=email.changed "
    "exchange=specproof.demo.events publishes=1"
)


def test_a_report_line_yields_the_count_the_routing_key_and_the_exchange() -> None:
    observation = parse_mq_observations(REPORT)
    assert observation["observed"] is True
    assert observation["publish_count"] == 1
    assert observation["routing_keys"] == ["email.changed"]
    assert observation["exchanges"] == ["specproof.demo.events"]


def test_an_output_without_a_report_line_observed_nothing() -> None:
    """Absence is recorded, not invented: no line means the test said
    nothing — NOT that it observed no publish."""
    observation = parse_mq_observations("Tests run: 1, Failures: 0, Errors: 0")
    assert observation["observed"] is False
    assert observation["publish_count"] == 0
    assert observation["routing_keys"] == []


def test_an_empty_output_observed_nothing() -> None:
    observation = parse_mq_observations("")
    assert observation["observed"] is False
    assert observation["publish_count"] == 0


def test_several_lines_are_summed_and_the_routing_keys_deduped() -> None:
    observation = parse_mq_observations(
        REPORT + "\n"
        + "SPECPROOF_MQ routing_key=email.changed "
        + "exchange=specproof.demo.events publishes=2\n"
        + "SPECPROOF_MQ routing_key=order.created "
        + "exchange=specproof.demo.events publishes=1"
    )
    assert observation["publish_count"] == 4
    assert observation["routing_keys"] == ["email.changed", "order.created"]
    assert len(observation["reports"]) == 3


def test_a_line_the_application_logged_is_not_a_report() -> None:
    """The marker is namespaced: an application's own line that happens
    to mention a routing key must not be read as a publish report."""
    observation = parse_mq_observations(
        "sent message routing_key=email.changed to the broker"
    )
    assert observation["observed"] is False


def test_an_unreadable_count_does_not_invent_a_number() -> None:
    observation = parse_mq_observations(
        "SPECPROOF_MQ routing_key=email.changed publishes=many"
    )
    assert observation["observed"] is True
    assert observation["publish_count"] == 0
    assert observation["routing_keys"] == ["email.changed"]


def test_the_parsed_shape_compares_with_the_collectors_comparison() -> None:
    """The parsed observation must speak the collector's vocabulary, so
    the two sides are compared by the SAME comparison the recorder
    path uses — not by a second one written here."""
    base = parse_mq_observations(REPORT)
    head = parse_mq_observations(
        "SPECPROOF_MQ routing_key=email.changed "
        "exchange=specproof.demo.events publishes=0"
    )
    comparison = compare_publish_observations(base, head)
    assert comparison["changed_count"] == 1
    assert comparison["changed"][0]["change"] == "publish_count_changed"
    assert comparison["changed"][0]["base"] == 1
    assert comparison["changed"][0]["head"] == 0


def test_the_payload_digests_are_empty_on_both_sides() -> None:
    """The test reports the routing key and the count, not the payload's
    bytes — so the comparison's payload dimension says nothing rather
    than pretending the payloads matched."""
    observation = parse_mq_observations(REPORT)
    assert observation["payload_digests"] == []
