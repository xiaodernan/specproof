# Case 53: Order Count Field Removed From User Response

The API response schema must remain backward-compatible: the orderCount field must stay present.

## Acceptance Criteria
1. GET /api/users responses must keep the orderCount field.
