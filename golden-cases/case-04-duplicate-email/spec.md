# Case 04: Duplicate Email Not Rejected

The uniqueness check for email addresses is removed from the service layer.
Duplicate emails can be inserted without error.

## Expected Finding
- Severity: BLOCKER
- Type: data_integrity
- Evidence: SQL constraint violation not enforced
