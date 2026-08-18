# Case 64: Cache TTL Tuned

Tuning the cache TTL is a benign configuration change; any positive TTL keeps the documented eviction semantics.

## Acceptance Criteria
1. Cache writes must still pass a positive TTL in seconds.
