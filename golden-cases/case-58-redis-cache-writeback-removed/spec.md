# Case 58: Cache Write-Back Removed

User reads must follow cache-aside: a cache miss must load from the database and write the entry back to the cache.

## Acceptance Criteria
1. A cache miss must write the entry back with a TTL.
