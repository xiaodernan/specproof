# Case 56: User Cache Not Evicted On Email Change

After an email change, the cached user entry must be evicted so subsequent reads see the new email.

## Acceptance Criteria
1. Changing the email must delete the user:cache:{id} entry.
