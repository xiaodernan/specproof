# Case 15: Whitespace-Only Re-Indent (False-Positive Trap)

The protected controller method is re-indented. The diff shows changed
lines, but semantics are identical — no finding may be emitted.

## Expected Finding
- Severity: NONE
- Type: none
- Evidence: pure re-indentation must NOT be flagged
