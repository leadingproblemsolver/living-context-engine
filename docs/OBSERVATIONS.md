# Observations

Everything the engine knows arrives as an **observation packet**. There are two
ways to produce one: the line syntax, and the JSON schema. They are equivalent —
the line parser emits exactly the same packet a model does.

## Line syntax

Any `.md`, `.txt`, `.yaml`, or `.yml` file in a configured source directory is
scanned. Lines that do not match the syntax are still stored as searchable
observation records, but they never become belief.

### Directives

Set defaults for every line below them in the file.

| Directive | Meaning |
| --- | --- |
| `@source <ref>` | Where this came from — recorded on every piece of evidence |
| `@kind <kind>` | Default evidence kind for the file |
| `@actor <who>` | Who is asserting it |
| `@date <iso8601>` | When it was observed (defaults to file mtime) |
| `@entity <kind> <name>` | Default subject for bare `claim:` lines |
| `@importance <0-1>` | Default importance |

### Statements

```
claim: <entity> / <attribute> = <value>
claim: <attribute> = <value>                 # uses the @entity default
unknown: <question>
decision: <what was decided>
risk: <what could go wrong>
blocker: <what is in the way>
relation: <entity> -[<relation>]-> <entity>
```

`decision:`, `risk:`, and `blocker:` each create an entity of that kind with a
`status` claim, so a decision being reversed later shows up as a state
transition rather than as a new note.

### Modifiers

A trailing `[key=value, key=value]` group:

| Key | Effect |
| --- | --- |
| `kind` | Evidence kind for this line only |
| `actor` | Who asserted this line |
| `importance` | 0–1, how much a wrong answer costs |
| `impact` | 0–1, for `unknown:` lines |
| `blocks` | The decision an unknown is blocking |
| `n` | How many independent observations this line stands for |
| `independent` | `false` when the `n` observations are one source repeated |
| `status` | Overrides the status value on `decision:` / `risk:` / `blocker:` |

`n=12` on an interview line means twelve respondents said it, and the engine
records twelve evidence rows. `n=12, independent=false` means one person said it
twelve times, and confidence barely moves.

### Attributes are single-valued

One entity has one `buyer`. Writing a different value for the same attribute is
how you tell the engine a belief changed — that is what makes the delta
meaningful. When something genuinely is a set, suffix the attribute:

```
claim: blockers[] = procurement approval
claim: blockers[] = IT security review
```

Multi-valued attributes accumulate instead of contesting each other.

### Fenced code is documentation

Anything inside a ``` fence is ignored. A README that shows the syntax must not
teach the graph what it demonstrates.

## Evidence kinds

Weakest to strongest, with the ceiling each one imposes on confidence:

| Kind | Weight | Ceiling |
| --- | --- | --- |
| `inference` | 0.05 | 0.50 |
| `assertion` | 0.08 | 0.60 |
| `third_party` | 0.12 | 0.70 |
| `public_source` | 0.12 | 0.70 |
| `document` | 0.15 | 0.75 |
| `interview` | 0.30 | 0.85 |
| `usage_data` | 0.30 | 0.92 |
| `measurement` | 0.32 | 0.93 |
| `transaction` | 0.34 | 0.95 |
| `experiment` | 0.35 | 0.95 |

Choose the weakest kind that honestly describes the source. The ceiling is the
mechanism that stops opinion from being laundered into certainty by volume.

Confidence is noisy-OR over the evidence, damped for repeats from the same
`(kind, actor)` pair, capped by the strongest method present, and then decayed
by age — `half_life_days` in `.lce/config.json` controls the decay, and a
belief never decays below half its stated strength.

## Observation packets (JSON)

Any `.json` or `.jsonl` file in a source directory is read as one or more
packets, and `lce absorb <file>` applies one directly. This is the interop
contract: anything that can emit this shape can drive the engine.

```json
{
  "source": {
    "ref": "pilots/2026-07-paid-pilot",
    "kind": "transaction",
    "actor": "billing-system",
    "observed_at": "2026-07-15T00:00:00+00:00"
  },
  "entities": [
    { "name": "Manufacturing Ops Managers", "kind": "segment", "aliases": ["mfg ops"] }
  ],
  "claims": [
    {
      "entity": "Manufacturing Ops Managers",
      "attribute": "willingness_to_pay",
      "value": "$1,500 per month, no procurement involvement",
      "importance": 0.95,
      "evidence": [
        {
          "excerpt": "Invoice PIL-0011 paid in full within 4 days, card, no PO raised.",
          "kind": "transaction",
          "actor": "acme-fabrication",
          "locator": "invoice PIL-0011"
        }
      ]
    }
  ],
  "relationships": [
    { "from": "Manufacturing Ops Managers", "to": "Compliance Exporter", "relation": "buys" }
  ],
  "unknowns": [
    { "question": "Do pilots renew after the first audit cycle?", "impact": 0.9,
      "blocks_decision": "raising the price" }
  ]
}
```

The machine-readable JSON Schema is embedded in every `lce prompt extract`
output, and lives in `living_context.observe.OBSERVATION_SCHEMA`.

A packet whose claim has an empty `evidence` array is rejected. That is the
single hardest rule in the system.

## What happens on ingest

For each packet:

1. The source is recorded with a content hash — re-ingesting an unchanged file
   adds nothing.
2. Entities are upserted by `(project, kind, normalised name)`.
3. Each claim is resolved to a `(entity, attribute, normalised value)` identity.
   Evidence is inserted idempotently, so re-reading a file never inflates
   confidence.
4. Confidence is recomputed from all evidence on that claim.
5. The claim is compared against whatever else is active in the same slot, and
   one transition is written: `established`, `reinforced`, `weakened`,
   `revised`, or `contested` — each with a rationale explaining the move.
6. Conflicts always produce a contradiction record. The new value supersedes the
   old one only when its effective confidence exceeds the incumbent's by 25%.
7. Unknowns and relationships are upserted.
8. Actions are re-ranked and an uncertainty snapshot is written.
