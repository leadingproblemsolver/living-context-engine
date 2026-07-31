# Discovery round one — manufacturing operations

@source interviews/2026-06-round-one
@kind interview
@date 2026-06-18
@entity segment Manufacturing Ops Managers

Fourteen calls, one hour each, plant operations managers at 50-500 person
manufacturers. Notes below are the claims the calls actually support.

claim: primary_pain = compliance reporting risk [importance=0.95, n=12]
claim: buyer = Department Head [importance=0.9, n=9]
claim: blockers[] = procurement approval above $10k [importance=0.8, n=7]
claim: blockers[] = IT security review for anything touching the MES [n=4]
claim: current_workaround = a shared spreadsheet plus a quarterly consultant [n=11]
claim: trigger_event = a failed or near-miss audit [importance=0.85, n=8]

Three of the fourteen volunteered that they had looked at automation tooling and
put it down again.

claim: attitude_to_automation = wary of anything that acts without a human sign-off [importance=0.7, n=3]

unknown: What do they currently spend on compliance reporting, in budget line terms? [impact=0.9, blocks=pricing tier]
unknown: Will a Department Head approve without procurement below $10k? [impact=0.8, blocks=self-serve pricing]
unknown: Who actually owns the audit failure when it happens? [impact=0.6]

relation: Manufacturing Ops Managers -[blocked_by]-> procurement approval above $10k
