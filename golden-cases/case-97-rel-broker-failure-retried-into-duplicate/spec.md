# Case 97: Broker Failure Retried Into Duplicate Event

order.created must be published exactly once: a transient broker failure must not be retried into a duplicate event.

## Acceptance Criteria
1. A failed publish must surface to the caller and must not be retried into a second order.created event.
