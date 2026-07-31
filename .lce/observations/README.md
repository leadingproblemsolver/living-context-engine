# Observations

Drop anything here that tells you something about reality: interview notes,
support threads, competitor pages, meeting notes, exported issues.

A worked example lives in `.lce/examples/first-observation.md` — copy it here to
watch the loop run.

Two things become **state**; everything else stays a searchable note.

## 1. Claim lines

```
@source interviews/2026-07-14-acme
@actor jane@acme.example
@date 2026-07-14
@kind interview
@entity segment Manufacturing Ops Managers

claim: primary_pain = compliance reporting risk [importance=0.9]
claim: buyer = Department Head
claim: blockers[] = procurement approval
claim: competitor Northwind / pricing = $1,200 per site per month [kind=public_source]
unknown: Will they pay more than $2k/month? [impact=0.9, blocks=pricing tier]
relation: Manufacturing Ops Managers -[blocked_by]-> procurement approval
```

- `@` directives set defaults for every line below them in the file.
- `claim: <entity> / <attribute> = <value>` — the entity part is optional when
  `@entity` is set.
- Attributes are **single-valued**. Writing a different value for the same
  attribute is how you tell the engine a belief changed. Suffix with `[]` when
  the attribute really is a set.
- `[key=value]` modifiers: `kind`, `actor`, `importance`, `impact`, `blocks`,
  `n` (how many independent observations this line stands for).
- `decision:`, `risk:`, and `blocker:` lines each create an entity with a
  `status` claim.

## 2. Observation packets

Any `.json` / `.jsonl` file here is read as an observation packet — the same
shape a model produces from `lce prompt extract`. Absorb them with:

```
lce absorb .lce/observations/packet.json
```

## Source kinds, weakest to strongest

`inference` · `assertion` · `third_party` · `public_source` · `document` ·
`interview` · `usage_data` · `measurement` · `transaction` · `experiment`

The kind you choose caps how confident the engine will ever be. No number of
people *saying* they would pay can reach the confidence of one of them paying.
