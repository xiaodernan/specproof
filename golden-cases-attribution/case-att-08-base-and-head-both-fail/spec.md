# Attribution Case: Duplicate Email Rejection (UNIQUE-01)

The change-email endpoint must reject duplicate emails: changing to an email that is already in use must fail, while changing to a fresh email must succeed.

# Attribution Case: Email Event Routing Key (EVENT_ONCE-01)

The change-email endpoint must publish the email.changed event exactly once to the documented routing key.
