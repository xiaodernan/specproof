# Case 13: Composed Custom Security Annotation (False-Positive Trap)

The @PreAuthorize annotation is replaced with a custom composed annotation
(@RequireAuth) that carries the same protection via a Spring Security
meta-annotation. Behaviour is unchanged; a naive diff reader that only
knows built-in annotation names will flag this as an auth regression.

## Expected Finding
- Severity: NONE
- Type: none
- Evidence: equivalent protection must NOT be flagged
