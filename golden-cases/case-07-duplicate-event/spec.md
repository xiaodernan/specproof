# Case 07: Event Published Multiple Times

The email-changed event is published once in the service method
and again in an event listener, causing duplicate events.

## Expected Finding
- Severity: MAJOR
- Type: duplicate_event
- Evidence: RabbitMQ message count > 1 per change
