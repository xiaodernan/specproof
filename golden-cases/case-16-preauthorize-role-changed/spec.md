# Case 16: Role Tightened (False-Positive Trap)

@PreAuthorize("isAuthenticated()") is changed to
@PreAuthorize("hasRole('ADMIN')") — MORE restrictive, not a regression.
A naive checker comparing annotation text may flag it; the verifier must
not treat tightened authorization as a security regression.

## Expected Finding
- Severity: NONE
- Type: none
- Evidence: tightened role must NOT be flagged
