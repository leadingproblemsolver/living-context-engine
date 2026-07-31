# Living Context in this repository

This repo keeps a machine-maintained model of what we currently believe, why we
believe it, and what to check next. It is not a document store.

## Daily use

```bash
lce ingest                       # read every configured source, diff, update state
lce delta                        # what changed and why
lce state                        # the current reality model
lce contradictions               # where the evidence disagrees with itself
lce actions --refresh            # ranked next validation actions
lce context "should we build X"  # a decision-scoped context pack
lce metric                       # uncertainty removed over time
```

## Adding an observation

Write it into `.lce/observations/` using the syntax in that folder's README, or
produce a packet with any assistant:

```bash
lce prompt extract --input notes/customer-call.md > /tmp/prompt.txt
# paste into an assistant, save the JSON reply
lce absorb /tmp/reply.json
```

With `ANTHROPIC_API_KEY` set, `lce ingest --llm notes/` does that round trip for
you.

## Rules that keep this useful

- Claims need evidence. A claim with no source is not recorded.
- Contradictions are kept, not resolved by whoever wrote last.
- Confidence is derived from evidence weight, source independence, and age —
  never typed in by hand.
