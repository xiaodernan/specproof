# Case 38: Read-Only Transaction On User Reads

User reads must stay transactional-safe; adding a read-only transaction must not change behavior.

## Acceptance Criteria
1. Reads must return the same data as before.
