# Case 18: Wrong Routing Key (Execution-Only Regression)

The change-email endpoint must publish the email.changed event to the
documented routing key. The diff is a string constant change that a static
diff reader cannot judge; only executing the publish and verifying the
invocation against the expected exchange/routing key reveals it.

## Expected Finding
- Severity: MAJOR
- Type: event_delivery
- Evidence: differential execution (mock RabbitTemplate invocation check)
