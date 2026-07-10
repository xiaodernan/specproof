# Case 01: Auth Bypass — @PreAuthorize Removed

A Spring Boot controller method with `@PreAuthorize("isAuthenticated()")` in Base
has the annotation removed in Head. Unauthenticated requests should return 401.

## Expected Finding
- Severity: BLOCKER
- Type: annotation_removed / static_analysis
- Evidence: Base requires auth (401), Head allows unauthenticated access (200)
