# Case 61: Token Pattern Typo

After an email change, session token keys matching the documented pattern token:user:{id}:* must be deleted; the user cache must also be evicted.

## Acceptance Criteria
1. Token invalidation must scan and delete the documented key pattern.
