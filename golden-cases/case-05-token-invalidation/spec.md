# Case 05: Token Invalidation Broken

Redis token invalidation logic is removed after email change.
Old tokens remain valid after email change.

## Expected Finding
- Severity: MAJOR
- Type: session_security
- Evidence: Redis key still exists after email change
