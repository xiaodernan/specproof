# Case 68: Order Publish Helper Extracted (Equivalent)

Extracting the order event publish into a private helper must keep delivery semantics identical.

## Acceptance Criteria
1. order.created must still be published exactly once with the documented exchange and routing key.
