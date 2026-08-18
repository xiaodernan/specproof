# Case 19: Silent Data Corruption (Execution-Only Regression)

The stored email must be unique and must equal the requested value exactly.
The diff is an innocuous string concatenation; only executing the change and
asserting the stored value equals the requested one reveals the corruption.

## Expected Finding
- Severity: MAJOR
- Type: data_integrity
- Evidence: differential execution (response email differs from request)
