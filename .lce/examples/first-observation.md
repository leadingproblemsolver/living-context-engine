# Sample observation. Copy this file into .lce/observations/ to try the loop.
# It lives outside the ingested sources on purpose: a new graph should start
# empty, not pre-seeded with beliefs nobody actually holds.

@source examples/first-interviews
@kind interview
@date 2026-07-20
@entity segment Manufacturing Ops Managers

claim: primary_pain = manual compliance reporting [importance=0.9, n=6]
claim: buyer = Department Head [importance=0.8, n=4]
claim: blockers[] = procurement approval [n=3]
unknown: Will a Department Head sign off without procurement? [impact=0.8, blocks=self-serve pricing]
unknown: What do they spend on compliance reporting today? [impact=0.9]

decision: start with the compliance report exporter [importance=0.7]
risk: the exporter is easy for an incumbent to copy
