# What makes this adoptable

The first seven invariants make the engine *correct*. These make it **adoptable** —
the difference between a tool that works for the person who built it and one that
works the same way for the tenth team that tries it.

Each one exists because a specific failure kills adoption.

## 8. Nothing inferred enters the graph unreviewed

**Failure it prevents:** the first time the engine confidently records something a
model made up, the user stops trusting the whole graph and never comes back.

Deterministic parsing of a file a human wrote is applied directly. Model
extraction, connector pulls, and API writes are **staged as proposals** — one per
claim, so a reviewer can accept the three that are right and reject the one that
is invented.

```bash
lce review                              # what is waiting, and why
lce review --accept <id> [<id> ...]
lce review --reject <id> --note "the model invented this"
lce review --accept-all --origin connector:csv
```

Policy lives in `.lce/config.json` as `auto_apply` (default `["parser","human"]`).
Add `"connector"` once you trust a source; the engine tells you when you should:

```
acceptance so far:
  connector:csv                92% accepted (23 yes / 2 no / 0 open)
  model                        61% accepted (14 yes / 9 no / 3 open)
```

**Acceptance rate per origin is the trust metric.** A source below ~70% is
costing more review time than it saves — fix its configuration or turn it off.

## 9. One thing has one name

**Failure it prevents:** silent forking. "Acme" and "Acme Inc." become two
entities, `primary_pain` and `main_pain` become two slots, and the delta property
dies — a new value never contests the old one, so the graph looks calmer than
reality.

Attribute drift is the worse of the two, because it *hides changes* rather than
just splitting them.

```bash
lce identity          # candidates, strongest first
lce identity --fix    # stage them as reviewable proposals
lce merge "Acme Fabrication" "Acme Fab" --reason "same company"
```

Entity candidates come from token overlap and character similarity, ignoring
corporate noise (`Inc`, `Ltd`, `GmbH`). Attribute candidates require a **shared
word and a shared entity** — something has to actually carry both slots for them
to be in conflict. The better-evidenced name survives; the other becomes an
alias, so future ingests land in the right slot automatically. Every merge is
recorded with its reason in the `merges` table.

## 10. Every claim knows which decision it serves

**Failure it prevents:** the engine becomes knowledge hygiene — pleasant,
unowned, and dropped after two weeks. Claims are not interesting in themselves;
they are interesting because a decision rests on them.

```bash
lce decision add "Which segment do we build for first?" --owner mel --auto-link
lce decision link <id> --claim <claim_id> --unknown <unknown_id>
lce decisions           # the board, with readiness for each
lce metric --decision <id>
```

Linking a claim to a decision raises its importance floor, which feeds straight
into action ranking — so registering a decision changes what the engine tells you
to do next.

Readiness is deliberately governed by the **weakest** load-bearing belief, not
the average, because a decision is only as sound as the claim most likely to be
wrong:

```
Which segment do we build for first?
  readiness 0.12  [open]  owner mel
  not yet — deciding now is a guess wearing a number
    0.24  Ops Managers.primary_pain = data collection from the floor
    0.53  Ops Managers.primary_pain = compliance reporting risk
    blocked by: Who has this problem badly enough to pay? (impact 0.95)
    conflict:   "Department Head" vs "VP Operations"
```

That output is the product. It is the sentence a founder needs and never gets.

## 11. The engine speaks first

**Failure it prevents:** pull-only tools get forgotten. If someone has to
remember to run `lce delta`, they won't.

```bash
lce digest                                  # markdown
lce digest --format slack --post-slack      # into the channel
lce digest --format html --output public/index.html
lce serve                                   # dashboard at /
```

The digest is the recurring artifact: what moved and why, what is newly in
conflict, which decisions became answerable, the next three moves, and how many
proposals are waiting. Everything else in the engine exists to produce it. Put it
on a cron or in CI and the loop maintains itself.

## 12. Every integration is the same shape

**Failure it prevents:** per-source special cases turn into a maintenance swamp,
and users can't add the one source they actually need.

One contract: **fetch → packet → stage.** A connector returns
`ConnectorResult(packets, cursor, notes)` and nothing else. It never writes
state; the engine stages what comes back. See [`CONNECTORS.md`](CONNECTORS.md).

```bash
lce connectors        # available, configured, and last-run state
lce pull              # fetch everything, stage it, advance the cursors
lce pull --dry-run    # see what would come in
```

A third-party system does not get to write your beliefs. It gets to propose them.

## 13. Adaptation is data, not a fork

**Failure it prevents:** every team invents its own attribute names, so nobody's
graph is comparable and nothing that worked for one team transfers to the next.

```bash
lce profiles
lce init --profile customer-discovery
```

A profile carries the entity kinds, the suggested attribute vocabulary, the
starter questions, and the evidence guidance for one kind of work —
`customer-discovery`, `product-decisions`, `security-posture`, `hiring`. The
mechanics never change; only the vocabulary does. The profile is injected into
the extraction prompt, so two people running the same profile in different
companies produce comparable graphs.

`security-posture` also drops `half_life_days` to 90, because a control verified
last year is not verified.

## 14. The graph answers "why do you say that"

**Failure it prevents:** an unexplainable number is an unusable number. Nobody
acts on `confidence: 0.53` they cannot interrogate.

```bash
lce why <claim_id>
```

```
Ops Managers.buyer = Department Head

  confidence      0.53 (stored 0.66 × age 0.81)
  evidence        3 rows, 3 independent source(s): 3×interview
  method ceiling  0.85 (interview)
  cited:
    - [interview] survey.csv#row 2 — We failed an audit in March...
  how it got here:
    - [reinforced] 1 new observation — now 3 interview from 3 sources; 0.51 -> 0.66
  disputed by:
    - [open] "Department Head" vs "VP Operations"
  to move it: more independent sources, or one stronger method
```

When a claim sits at its method ceiling, the engine says so explicitly — *nothing
of the same kind will help*. That single line changes what people do next more
than any other output.

---

## The three adoption shapes

Most teams land in one of these. Pick one; do not try to do all three at once.

### 1. Repo-native (a team that already lives in git)

```bash
lce init --ci
# write observations into .lce/observations/ as you learn things
# CI ingests, ranks, and posts the digest on every push
```

Cost: one folder and a workflow. Nobody has to change tools.

### 2. Assistant-native (the fastest path to value)

```bash
lce init --profile customer-discovery
lce mcp --print-config    # paste into Claude Desktop / claude mcp add
```

Now the assistant your team already talks to can read the graph, cite confidence,
and propose observations from whatever it just read — which land in `lce review`.
No new interface, no syntax to learn.

### 3. Pipeline-native (research or ops at volume)

```bash
lce init --connectors
# point the csv connector at your survey export, enable github_issues,
# have Zapier/n8n drop packets into .lce/inbox or POST to /api/observations
lce pull && lce review
```

Cost: one config file. Evidence arrives where it already lives.

## What to measure in week one

Three numbers tell you whether adoption is real:

| Number | Where | What it means |
| --- | --- | --- |
| Proposal acceptance rate per origin | `lce review` | whether the sources are worth their review cost |
| Decisions with readiness ≥ 0.7 | `lce decisions` | whether the graph is actually answering anything |
| Uncertainty removed per hour | `lce metric` | whether the loop is moving |

Uncertainty going **up** in week one is correct and expected — that is the engine
finding out what you did not know. Watch the decision board instead.
