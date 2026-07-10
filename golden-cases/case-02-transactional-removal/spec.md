# Case 02: Transactional Annotation Removed

The `@Transactional` annotation is removed from a service method that performs
multi-step database operations. Could cause data inconsistency.

## Expected Finding
- Severity: MAJOR
- Type: annotation_removed
- Evidence: Static detection of @Transactional removal
