# Case 41: Orders Table Dropped From Schema

The orders table must keep existing in the schema migration scripts; dropping it breaks every order write in production.

## Acceptance Criteria
1. The orders table must not be dropped.
