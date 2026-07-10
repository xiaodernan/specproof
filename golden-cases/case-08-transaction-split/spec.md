# Case 08: Transaction Boundary Broken

Database operations that should be in the same transaction
are split across separate method calls without @Transactional.

## Expected Finding
- Severity: MAJOR
- Type: transaction_boundary
- Evidence: Static detection of missing @Transactional
