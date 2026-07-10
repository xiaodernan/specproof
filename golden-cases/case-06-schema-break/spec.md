# Case 06: API Schema Breaking Change

A response field is renamed from `userId` to `user_id`, breaking
backward compatibility with existing API consumers.

## Expected Finding
- Severity: MAJOR
- Type: schema_break
- Evidence: OpenAPI diff shows schema change
