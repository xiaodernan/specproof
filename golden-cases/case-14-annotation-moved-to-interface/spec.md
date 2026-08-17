# Case 14: Security Annotation Moved to Interface (False-Positive Trap)

The @PreAuthorize annotation is moved from the controller method to the
implemented interface method (JDK dynamic proxy resolves interface-level
method security in Spring). Behaviour is unchanged; static readers that
only scan the controller file will flag this as an auth regression.

## Expected Finding
- Severity: NONE
- Type: none
- Evidence: interface-level protection must NOT be flagged
