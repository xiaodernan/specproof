# Case 100: Event Timestamp Nulled

The email.changed event payload must stay intact: the timestamp must be set at publish time.

## Acceptance Criteria
1. The published event must carry a non-null timestamp.
