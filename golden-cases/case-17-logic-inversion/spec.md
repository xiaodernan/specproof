# Case 17: Inverted Uniqueness Guard (Execution-Only Regression)

The duplicate-email guard is inverted in the service layer: duplicate
emails are now accepted and unused emails are rejected. The diff is a
single character (!) that a static diff reader cannot judge without
executing the behaviour.

## Expected Finding
- Severity: BLOCKER
- Type: data_integrity
- Evidence: differential execution (base rejects the duplicate, head accepts it)
