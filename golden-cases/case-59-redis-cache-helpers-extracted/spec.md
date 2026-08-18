# Case 59: Cache Helpers Extracted (Equivalent)

Refactoring the cache read/write into private helpers must keep cache-aside semantics identical.

## Acceptance Criteria
1. Cache reads, write-back and TTL behave exactly as before.
