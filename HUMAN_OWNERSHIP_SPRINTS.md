# Human Ownership Sprints

1. Rebuild source replacement and prove stale records disappear after a file changes.
2. Hand-derive the confidence of a claim with mixed evidence kinds and repeated
   actors, then check it against `confidence_from_evidence`.
3. Construct a case where the supersession margin makes the wrong call, and
   argue for a different margin with evidence.
4. Add one new evidence kind end to end: weight, ceiling, schema enum, action
   routing, and tests.
5. Debug a malformed observation packet without weakening valid-packet behaviour.
6. Whiteboard ingestion → extraction → delta → contradiction → action → metric
   and explain every failure mode, including the ones the ceilings do not cover.
