# Living Context Engine

A reality delta compiler. You feed it messy observations — interview notes,
competitor pages, forum threads, pilot invoices, your own assumptions — and it
maintains a traceable model of **what you currently believe, why, how sure you
are, where the evidence disagrees with itself, and what to check next**.

It is not a document store. Files are only observation sources; the thing that
persists is state.

```
observations → extraction → comparison with current state → detected delta
    → evidence graph → uncertainty → verification actions → updated model
```

Local-first, dependency-free, one SQLite file. No account and no API key
required.

## Ten minutes, in any repository

```bash
pip install living-context-engine

cd your-repo
lce init --profile customer-discovery   # config, vocabulary, starter questions
lce ingest examples/discovery           # read sources, diff, record what changed
lce state                               # what you believe now
lce delta                               # what changed, and why it changed
lce contradictions                      # where the evidence disagrees with itself
lce why <claim_id>                       # why do you say that, and what would move it
lce decision add "Should we build the exporter first?" --auto-link
lce decisions                            # can this be decided yet, and what is blocking it
lce actions --refresh                    # ranked next validation actions
lce digest                               # the weekly what-changed summary
```

Run that against the bundled `examples/discovery` corpus — fourteen customer
interviews, a competitor's pricing page, a forum thread, founder notes, and
three paid pilot invoices — and part of what comes back is:

```
Manufacturing Ops Managers  [segment]
  buyer                    Department Head        [conf 0.91 · 10 evidence]
  buyer                    VP Operations          [conf 0.07 · 1 evidence]
  primary_pain             compliance reporting risk        [conf 0.76 · 21 evidence]
  primary_pain             data collection from the floor   [conf 0.62 · 11 evidence]
  willingness_to_pay       $1,500/month, no procurement     [conf 0.68 · 3 evidence]
```

The founder's belief that the buyer is a VP is still in the graph, at the
confidence one unsupported assertion earns, sitting next to the customer
evidence that disagrees with it. That juxtaposition is the product.

## What it enforces

**State, not content.** The primitive is `entity + attribute + value + evidence
+ confidence`, never a stored document. Prose is ingested as searchable
observation records but never becomes belief; only explicit statements do.

**No floating claims.** Every claim answers where it came from, who asserted it,
when, what supports it, and how sure we are. A claim submitted without evidence
is rejected, not stored with a shrug.

**Confidence is computed, never typed.** It derives from evidence weight, source
independence, and age — with two rules that matter:

- *Repetition is not corroboration.* Ten quotes from one person move belief far
  less than one quote each from ten people.
- *Method ceilings.* Each kind of evidence caps how confident the engine can
  ever become. No number of people **saying** they would pay reaches the
  confidence of one of them **paying**. Interviews cap at 0.85; transactions and
  experiments can go higher.

**Contradictions are objects, not errors.** When a new value conflicts with an
existing one the engine always records the conflict. It supersedes the old
belief only when the new evidence clearly outweighs it; otherwise both stay
active and the conflict stays open, because a near-tie is information.

**Retrieval is task-specific.** `lce context "<question>"` generates a pack for
that decision — relevant entities, the transitions that moved them,
contradictions in scope, open unknowns, next actions. Two questions produce two
different packs.

**Every uncertainty produces an action.** Open questions, unresolved conflicts,
and weakly-held-but-important beliefs compile into ranked verification tasks,
scored by expected uncertainty removed per unit of effort. Questions about
behaviour route to experiments, because interviews cannot settle them.

**The metric is uncertainty removed per unit time.** Not documents ingested, not
tokens. `lce metric` reports the current uncertainty load and its rate of
change, and `lce metric --decision <id>` scopes it to one decision. Ingesting
usually *raises* it at first — that is the engine finding out what you did not
know.

**Nothing inferred enters the graph unreviewed.** Deterministic parsing of a file
a human wrote is applied directly. Model extraction, connector pulls, and API
writes are staged as proposals — one per claim — and `lce review` reports the
acceptance rate per source so you can see which ones are worth their review cost.

**Claims exist to serve decisions.** Register the decision, link the evidence, and
the engine tells you whether it can be decided yet — governed by the *weakest*
load-bearing belief, because that is the one most likely to be wrong.

Six more adoption invariants, and why each one exists, are in
[`docs/ADOPTION.md`](docs/ADOPTION.md).

## Getting observations in

Three routes, all producing the same internal packet:

1. **Write them.** A small line syntax, in any Markdown or text file:

   ```
   @source interviews/2026-06-round-one
   @kind interview
   @entity segment Manufacturing Ops Managers

   claim: primary_pain = compliance reporting risk [importance=0.95, n=12]
   claim: buyer = Department Head [n=9]
   unknown: What do they spend on this today? [impact=0.9, blocks=pricing tier]
   ```

2. **Have any assistant write them.** No API key needed:

   ```bash
   lce prompt extract --input notes/customer-call.md > prompt.txt
   # paste prompt.txt into an assistant, save the JSON reply as reply.json
   lce absorb reply.json
   ```

   The prompt embeds your existing entity vocabulary and current beliefs, so the
   model extracts *deltas against what you already know* rather than isolated
   summaries.

3. **Let the engine call the model.** `pip install 'living-context-engine[llm]'`,
   set `ANTHROPIC_API_KEY`, then `lce ingest --llm notes/`.

See [`docs/OBSERVATIONS.md`](docs/OBSERVATIONS.md) for the full syntax and the
packet schema.

## The prompt library

`lce prompts` lists them; each renders with your live state injected.

| Prompt | What it produces |
| --- | --- |
| `extract` | Raw source → observation packet |
| `interview-guide` | A research guide targeting your current open unknowns |
| `adjudicate` | What kind of conflict this is, and what would settle it |
| `actions` | A sequenced two-week validation plan from the ranked actions |
| `decision-brief` | An answer to one decision, from the scoped context pack |
| `review-delta` | An audit of recent belief changes for over-confidence |

See [`docs/PROMPTS.md`](docs/PROMPTS.md).

## Plugging into what you already use

**Inside your assistant.** `lce mcp` runs the engine as an MCP server, so Claude
Desktop, Claude Code, or Cursor can read the graph, cite its confidence, and
propose observations from whatever it just read:

```bash
lce mcp --print-config          # paste into your MCP client
```

Proposals land in `lce review` — the assistant gets to be useful and wrong
without touching the graph. See [`docs/MCP.md`](docs/MCP.md).

**From the systems evidence already lives in.** One connector contract, four built
in — spreadsheet exports (with population roll-up), GitHub issues, a Slack export,
and a drop folder anything can write into:

```bash
lce connectors     # available, configured, last run
lce pull           # fetch, stage for review, advance cursors
```

Plus a single write endpoint (`POST /api/observations`, separate write token,
idempotency keys) for Zapier, n8n, Make, or your own service. See
[`docs/CONNECTORS.md`](docs/CONNECTORS.md).

**Where the team already reads.** `lce digest` renders the recurring what-changed
summary as Markdown, Slack, HTML, or JSON, and posts to a Slack webhook or a CI
artifact. `lce serve` exposes a dashboard at `/`.

**Everything else:** the `lce` CLI, `.lce/config.json` per repository, one SQLite
file you can query directly, JSON/CSV export of either layer, and a read-only
HTTP API across state, delta, contradictions, unknowns, actions, decisions,
proposals, metric, digest, and context.

See [`docs/ADOPTION.md`](docs/ADOPTION.md),
[`docs/INTEGRATION.md`](docs/INTEGRATION.md), and [`docs/API.md`](docs/API.md).

## What this is not

Extraction from the line syntax is deterministic pattern matching, not
understanding; model-assisted extraction is only as good as the model.
Confidence is a bookkeeping device for evidence strength, independence, and age
— it is not a probability that a claim is true. The graph is only as honest as
the source `kind` you assign. And nothing here decides anything: it makes the
state of your knowledge, and the cost of your remaining ignorance, explicit
enough to argue with.

`lce validate` re-derives every claim's confidence from its evidence and fails
if the stored graph has drifted from its own provenance.
