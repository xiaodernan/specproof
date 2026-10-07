"""Drill — notify outbox delivery mechanics (DRILLS.md, #16.6-1).

Executes against the live local MySQL; the webhook endpoint is SYNTHETIC
(a recording connector): what this drill proves is the outbox state
machinery on a real database — claim, deliver-mark, no-redelivery — not
the HTTP endpoint (that is the connector's own contract, tested in
tests/unit/test_notify_connector.py).

Sequence:

1. Create one job row (QUEUED).
2. Simulate the worker's accepted terminal write:
   transition_job_status_with_notify puts the verdict AND the built
   notification into notify_outbox in one transaction.
3. Crash window: the relay has not run. The intent is durable; a SIGKILL
   here loses nothing but the announcement is still owed.
4. First relay cycle: the connector accepts; delivered_at is stamped and
   the row leaves the claim set.
5. Second relay cycle: no re-delivery — the claim excludes delivered rows,
   so a duplicate announcement is a relay defect.

Pass criteria: enqueued == 1, delivered == 1, dead_lettered == 0 after the
first cycle, and the second cycle changes nothing (attempts included).

Exit codes: 0 = PASS, 1 = FAIL, 2 = infrastructure unavailable.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from typing import Any, cast

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.notify.protocol import (  # noqa: E402
    Notification,
    SendStatus,
)
from ops.drills import (  # noqa: E402
    NotifyIntentStore,
    notify_intent_counts,
)
from storage.mysql import MySQLStore  # noqa: E402
from storage.notify_relay import NotifyOutboxRelay  # noqa: E402


class RecordingConnector:
    """Synthetic receiver: accepts everything, records what reached it."""

    name = "drill-recording"
    capabilities: frozenset[str] = frozenset()

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> SendStatus:
        self.sent.append(notification)
        return SendStatus.SENT

    def close(self) -> None:
        return None


def run_drill(mysql: MySQLStore) -> dict[str, Any]:
    job_id = "drill-notify-" + uuid.uuid4().hex[:12]

    payload = {
        "event_type": "verification.verified",
        "title": "SpecProof verification passed",
        "text": "Verdict: VERIFIED (drill)",
        "blocks": [],
        "job_id": job_id,
    }

    # 1. One QUEUED job row (the drill owns it end to end).
    job_id_value = job_id
    mysql.create_job_with_outbox({
        "id": job_id_value,
        "repo_path": REPO_ROOT.as_posix() + "/demo/spring-backend",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": "spec.md",
        "depth": "FAST",
    })
    # 2. The worker's accepted terminal write, intent riding along: the
    # claim (QUEUED->RUNNING) mirrors the real worker, then the verdict.
    if not mysql.transition_job_status(
        job_id_value, "RUNNING", from_status="QUEUED", worker_id="drill",
    ):
        return {"passed": False, "verdict": "FAIL — claim refused"}
    written = mysql.transition_job_status_with_notify(
        job_id_value, "VERIFIED", from_status="RUNNING",
        summary={"verdict": "VERIFIED"},
        notify_payload=payload,
    )
    if not written:
        return {"passed": False, "verdict": "FAIL — terminal write refused"}

    # 3. Crash window: relay has not run. The intent is already durable.
    before = notify_intent_counts(cast(NotifyIntentStore, mysql), job_id)
    if before != {"enqueued": 1, "delivered": 0, "dead_lettered": 0,
                  "attempts_total": 0}:
        return {"passed": False, "verdict": f"FAIL — crash window wrong: {before}"}

    # 4-5. Two relay cycles: deliver once, then never again.
    connector = RecordingConnector()
    relay = NotifyOutboxRelay(
        mysql=mysql, connector_factory=lambda: connector, poll_interval=0.0,
    )
    first = relay.drain_pending()
    after_first = notify_intent_counts(cast(NotifyIntentStore, mysql), job_id)
    second = relay.drain_pending()
    after_second = notify_intent_counts(cast(NotifyIntentStore, mysql), job_id)
    # The claim set is GLOBAL (any due row), so first/second may include
    # intents orphaned by earlier crashed runs — that is the at-least-once
    # promise WORKING, not noise. The per-job facts are the assertions:
    # this job's row is delivered exactly once, and the second cycle
    # changes nothing for it (delivered rows leave the claim set).
    own_deliveries = sum(
        1 for n in connector.sent if n.job_id == job_id
    )

    passed = bool(
        after_first == {"enqueued": 1, "delivered": 1,
                        "dead_lettered": 0, "attempts_total": 1}
        and after_second == after_first
        and own_deliveries == 1
    )
    return {
        "passed": passed,
        "job_id": job_id,
        "verdict": (
            "PASS — intent survived the crash window, delivered exactly once"
            if passed else "FAIL — delivery mechanics violated"
        ),
        "before": before,
        "after_first": after_first,
        "after_second": after_second,
        "relay_first": first,
        "relay_second": second,
        "own_deliveries": own_deliveries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        mysql = MySQLStore()
        mysql.ensure_tables()
    except Exception as exc:
        print(f"INFRA UNavailable: {exc}", file=sys.stderr)
        return 2
    started = time.time()
    result = run_drill(mysql)
    result["elapsed_seconds"] = round(time.time() - started, 2)
    print(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
