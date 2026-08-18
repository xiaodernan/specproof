# Case 78: Email Input Trimmed

Normalizing the email input with trim() must not change the rejection and persistence semantics.

## Acceptance Criteria
1. Valid emails keep their exact value; invalid values are still rejected.
