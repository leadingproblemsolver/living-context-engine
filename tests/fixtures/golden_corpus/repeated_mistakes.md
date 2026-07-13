# Repeated mistakes

Blocker: the retry queue silently dropped jobs under load because errors were swallowed without logging.
Blocker: silently swallowing retry queue errors under load caused dropped jobs again in a later incident.

Decision: all retry queue error paths must now log and increment a metric instead of swallowing exceptions.
