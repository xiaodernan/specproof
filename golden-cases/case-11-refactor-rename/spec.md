# Case 11: Refactor — Method Renamed (Semantic No-Op)

The controller method getUser() was renamed to fetchUser(). The HTTP
endpoint surface (verb + path) is unchanged; only the internal Java method
name changed.

## Expected Finding
- Severity: NONE
- Type: none (pure refactor — must NOT be flagged)
