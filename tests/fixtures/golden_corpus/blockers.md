# Blockers

Blocker: The payment retry queue cannot process more than 200 jobs per minute under current load.
This is blocking the checkout redesign rollout until the queue is scaled.

Blocker: Missing production credentials for the reporting service are blocking the weekly export job.

The payment retry queue blocker was resolved on a later date by adding a second worker pool.
