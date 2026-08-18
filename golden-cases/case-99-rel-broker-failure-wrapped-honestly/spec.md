# Case 99: Broker Failure Wrapped Honestly

order.created must be published exactly once: a broker failure may be re-thrown with a clearer message, but it must never duplicate the event.

## Acceptance Criteria
1. A failed publish must surface to the caller exactly once.
