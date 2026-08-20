# Attribution Case: Optimistic Locking (CONCURRENCY-01)

Product stock updates must use optimistic concurrency control (@Version): a stale write must be rejected, never silently overwritten.
