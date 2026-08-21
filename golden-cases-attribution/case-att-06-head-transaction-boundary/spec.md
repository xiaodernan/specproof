# Attribution Case: Transaction Boundary (TRANSACTION-01)

Cancelling an order must run inside a transaction so the status change and the stock restore stay atomic.
