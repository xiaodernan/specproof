# Case 20: Validation Relaxed (Execution-Only Regression)

The email field must reject blank values: the uniqueness constraint alone
does not cover empty input. Only executing a blank-email change proves the
acceptance regression.

## Expected Finding
- Severity: MAJOR
- Type: validation
- Evidence: differential execution (base 400, head 200)
