# Case 101: Stock Decrement Written By A Bulk Update

A concurrent stock decrement must not be lost. The service's write must go through the versioned entity, so that a stale read is rejected instead of silently overwriting the other writer's change. A bulk UPDATE that writes back the value the service read carries no version predicate: the lost update lands.

## Acceptance Criteria
1. A stale stock read must not overwrite the other writer's value.
2. The service must reject the stale write, not silently accept it.
