# Case 30: Version Guard Moved To Getter (Equivalent)

Product stock updates must use optimistic concurrency control: a stale write must be rejected.

## Acceptance Criteria
1. A stale write must be rejected exactly as before the refactor.
