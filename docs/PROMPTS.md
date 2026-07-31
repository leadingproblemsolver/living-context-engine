# The prompt library

Every prompt is rendered against your live graph, so it carries your entity
vocabulary, your current beliefs, your open unknowns, and your ranked actions.
They are designed to be pasted into any assistant — no API key, no integration.

```bash
lce prompts                              # list them
lce prompt <name> [options]              # print to stdout
lce prompt <name> --output prompt.txt    # or to a file
```

## `extract`

Turns raw source material into an observation packet.

```bash
lce prompt extract --input notes/customer-call.md > prompt.txt
# paste into an assistant, save the JSON reply
lce absorb reply.json
```

It embeds the JSON schema, your existing entity and attribute names, and your
current beliefs. That last part is what makes it a *delta* extractor rather than
a summariser: the model can see what you already think and is told to record
disagreement rather than smooth it over.

Without `--input` it prints a template with a placeholder for pasting the source
in yourself.

## `interview-guide`

```bash
lce prompt interview-guide --count 8
```

Takes your highest-impact open unknowns and weakest important beliefs and asks
for a research guide that would close them — including a rule that any question
about money, switching, or future behaviour must be rewritten as a question
about the past or an observable artifact, and a falsification note naming what
answer would prove each belief wrong.

Ends with the exact `claim:` lines to write down afterwards, so the results come
straight back into the graph.

## `adjudicate`

```bash
lce prompt adjudicate --id <contradiction_id>   # or omit --id for all open ones
```

Presents both sides of a conflict with their full evidence and asks for the
*kind* of conflict — measurement, population, temporal, stated-vs-revealed,
authority, or genuine — before asking for the cheapest observation that would
retire one side. It also asks whether the decision is even different under the
two beliefs; often it is not, and the conflict can wait.

## `actions`

```bash
lce prompt actions --count 10
```

Takes the engine's ranked proposals and asks for a sequenced two-week plan:
merge what one conversation could answer together, front-load the results that
change later work, flag any method that cannot settle its target, and give each
item a stopping rule.

## `decision-brief`

```bash
lce prompt decision-brief --task "should we build the exporter first"
```

Embeds a full task-scoped context pack and asks for a recommendation, the two or
three beliefs it rests on, and an explicit answer to whether the evidence
supports deciding at all yet. The model is instructed not to use knowledge
outside the pack, and to name the missing claim rather than fill the gap.

## `review-delta`

```bash
lce prompt review-delta --limit 30
```

An audit pass over recent transitions: was repetition counted as corroboration,
did a louder recent source overwrite a better-evidenced older one, is a
contested pair actually two different questions sharing an attribute name, did a
belief move without the world moving.

Worth running after any large ingest, and after any `--llm` run.

## Closing the loop by hand

The engine never needs network access. The full cycle without an API key:

```bash
lce prompt extract --input raw/thread.md > prompt.txt   # 1. render
#                                                         2. paste, get JSON
lce absorb reply.json                                   # 3. absorb
lce delta                                               # 4. see what moved
lce prompt actions > plan.txt                           # 5. plan the next round
```

With `pip install 'living-context-engine[llm]'` and `ANTHROPIC_API_KEY` set,
`lce ingest --llm <path>` performs steps 1–3 for every file in one command. It
uses the same prompt text, so the two paths produce the same packets.
