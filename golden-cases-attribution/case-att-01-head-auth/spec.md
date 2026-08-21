# Attribution Case R1: Authorization Guard Removed (head-introduced)

The change-email endpoint must require authentication: unauthenticated requests must receive 401 Unauthorized and must not modify the stored email.
