# Case 57: Cache TTL Removed

Cached user entries must carry a bounded TTL so stale entries expire.

## Acceptance Criteria
1. Cache writes must pass a positive TTL in seconds.
