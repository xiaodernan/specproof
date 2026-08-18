# Case 63: Cache Write Uses Different Key

Cache reads and writes must use the same documented key user:cache:{id}.

## Acceptance Criteria
1. A cache miss must write to the key that later reads consult.
