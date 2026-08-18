# Case 60: Cache Evicted Before The Save

The cache must be evicted AFTER the database write, so a concurrent reader can never repopulate a stale entry.

## Acceptance Criteria
1. The cache delete must happen after the user row is saved.
