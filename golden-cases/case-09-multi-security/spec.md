# Case 09: Multiple Security Issues

Multiple security annotations are removed simultaneously:
@PreAuthorize and @Secured are both removed from different endpoints.

## Expected Finding
- Severity: BLOCKER (multiple)
- Type: multiple annotation_removed
- Evidence: Multiple static analysis findings
