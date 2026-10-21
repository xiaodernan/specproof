"""The publish facts a test reported about itself.

The RabbitMQ surface cannot be observed from OUTSIDE the test's JVM
(#354): the pipeline runs the generated test with Maven surefire, so
the publish happens inside the test's own process, and from out here
there is no broker-side view of it.

What IS available is the test's own report. The generated test counts
the publishes it asserted and prints them in a machine-readable line::

    SPECPROOF_MQ routing_key=email.changed exchange=specproof.demo.events publishes=1

This module reads those lines out of a captured test output. It does
not judge them: the counts and routing keys are facts, and comparing
two sides is the collector's job (``compare_publish_observations``).

The discipline the rest of this project keeps: absence is recorded, not
invented. An output with no report line yields ``observed: False`` —
"the test said nothing" is NOT "the test observed no publish".
"""

from __future__ import annotations

import re
from typing import Any

#: The marker the generated test prints. Namespaced so it can never be
#: confused with the application's own log lines.
MQ_REPORT_PREFIX = "SPECPROOF_MQ"

#: One report line: the marker, then key=value pairs.
_MQ_REPORT_RE = re.compile(
    r"SPECPROOF_MQ\s+(?P<pairs>[A-Za-z_][A-Za-z0-9_]*=[^\s]+"
    r"(?:\s+[A-Za-z_][A-Za-z0-9_]*=[^\s]+)*)"
)

#: One key=value pair inside a report line.
_PAIR_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s]+)")


def parse_mq_observations(text: str | None) -> dict[str, Any]:
    """The publish facts a captured test output reports.

    The shape matches the collector's publish observation vocabulary
    (``publish_count`` / ``routing_keys`` / ``exchanges`` /
    ``payload_digests``), so the two sides can be compared with
    ``compare_publish_observations`` instead of a second comparison.

    ``observed`` says whether the test reported at all. The payload
    digests are always empty: the test reports the routing key and the
    count, not the payload's bytes — so the comparison's payload
    dimension is empty on both sides and says nothing (rather than
    pretending the payloads matched).
    """
    routing_keys: list[str] = []
    exchanges: list[str] = []
    reports: list[dict[str, Any]] = []
    total = 0
    for match in _MQ_REPORT_RE.finditer(text or ""):
        pairs = dict(_PAIR_RE.findall(match.group("pairs")))
        routing_key = pairs.get("routing_key", "")
        exchange = pairs.get("exchange", "")
        try:
            count = int(pairs.get("publishes") or 0)
        except ValueError:
            count = 0
        if routing_key and routing_key not in routing_keys:
            routing_keys.append(routing_key)
        if exchange and exchange not in exchanges:
            exchanges.append(exchange)
        total += count
        reports.append({
            "routing_key": routing_key,
            "exchange": exchange,
            "publishes": count,
        })
    return {
        "observed": bool(reports),
        "publish_count": total,
        "routing_keys": sorted(routing_keys),
        "exchanges": sorted(exchanges),
        "payload_digests": [],
        "reports": reports,
    }


__all__ = ["MQ_REPORT_PREFIX", "parse_mq_observations"]
