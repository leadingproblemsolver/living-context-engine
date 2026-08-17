# Connectors and the write API

Everything that brings observations in obeys one contract, and none of it writes
state directly. A connector proposes; a human accepts.

## The contract

```python
class Connector:
    name: str
    description: str
    required_config: tuple[str, ...]
    example: dict

    def fetch(self, config: dict, cursor: str, root: Path | None = None) -> ConnectorResult: ...
```

`ConnectorResult(packets, cursor, notes)`:

- `packets` — observation packets (see [`OBSERVATIONS.md`](OBSERVATIONS.md))
- `cursor` — an opaque high-water mark, stored per project and connector id
- `notes` — anything the operator should know: truncation, skipped rows, warnings

That is the entire interface. There is no per-source branch anywhere in the
engine, which is why writing your own takes an afternoon.

## Configuration

`.lce/connectors.json` — `lce init --connectors` writes a starting version.

```json
{
  "connectors": [
    {
      "name": "csv",
      "id": "q3-survey",
      "enabled": true,
      "config": { "path": "research/q3.csv", "entity_column": "company", "...": "..." }
    }
  ]
}
```

`id` lets you run several instances of one connector; the cursor is keyed by `id`.

```bash
lce connectors        # available, configured, and last-run state
lce pull              # fetch, stage, advance cursors
lce pull --connector q3-survey
lce pull --dry-run    # what would come in, without staging it
lce pull --reset      # ignore the cursor and re-read everything
```

Re-reading is always safe: evidence is idempotent, so nothing inflates.

## Built in

### `csv` — spreadsheet exports

The format research actually arrives in. Survey tools, CRMs, and interview
trackers all export a table; one row becomes one observation.

```json
{
  "path": "research/q3-survey.csv",
  "entity_column": "company",
  "entity_kind": "company",
  "actor_column": "respondent",
  "date_column": "responded_at",
  "kind": "interview",
  "claims": { "primary_pain": "biggest_problem", "buyer": "who_signs" },
  "unknown_columns": ["what_we_still_dont_know"],
  "excerpt_column": "verbatim",
  "importance": 0.7,
  "roll_up": {
    "entity": "Manufacturing Ops Managers",
    "kind": "segment",
    "attributes": ["primary_pain", "buyer"]
  }
}
```

**`roll_up` is the part that matters.** Without it you get one weak claim per
company and never form the population-level belief you actually decide on. With
it, each row also becomes *independent evidence* for the segment — so four
respondents agreeing produces a segment claim held at 0.53, the one dissenter
produces a contested minority view, and the per-company claims stay separately
attributable.

A bad column mapping fails immediately, naming the columns that exist.

### `github_issues` — where teams already write

Issues and comments as observations. The claim syntax works inside an issue body,
so a team can adopt the engine without leaving the tracker. A labelled issue
(`question`, `research`) with no explicit statement still contributes its title as
an open question.

```json
{
  "repo": "owner/name",
  "labels": ["research"],
  "state": "all",
  "kind": "document",
  "token_env": "GITHUB_TOKEN",
  "include_comments": true
}
```

Cursor is the issue `updated_at`, so re-pulls are cheap.

### `slack_export` — no app install required

Reads a Slack **export directory** rather than the API, deliberately: a team can
try the engine on last quarter's conversations without asking anyone to install an
app. Messages default to `assertion` strength, because that is what they are.

```json
{ "path": "~/Downloads/slack-export", "channels": ["product", "research"], "kind": "assertion" }
```

Only lines using the claim syntax become state. For unstructured discussion, run
the text through `lce prompt extract` instead.

### `filedrop` — the escape hatch

A landing directory anything can write into: `.json` / `.jsonl` packets, or
`.md` / `.txt` notes. This is what makes the engine reachable from tools it has
never heard of — Zapier, n8n, Make, a cron job, a Shortcut, a mail rule. Write a
file, `lce pull` stages it, processed files move to `_processed/`.

```json
{ "path": ".lce/inbox", "kind": "document", "archive": true }
```

## The write API

One POST endpoint, and it stages rather than applies.

```bash
export LCE_API_TOKEN=read-token
export LCE_API_WRITE_TOKEN=a-different-write-token   # required, and must differ
lce serve --host 0.0.0.0 --port 8790
```

```bash
curl -X POST http://127.0.0.1:8790/api/observations \
  -H "Authorization: Bearer $LCE_API_WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: call-2026-08-17-omar" \
  -d '{ "project": "acme", "packets": [ { "source": {...}, "claims": [...] } ] }'
```

- A **read token can never write.** The server refuses to start if the two tokens
  match.
- `Idempotency-Key` makes a retry safe; the same key replays the stored response.
- Body limit 5 MB. Accepts one packet, `{"packets": [...]}`, or a bare array.
- A packet whose claim has no evidence is rejected and named in `rejected`.

Everything else in the API stays read-only. Accepting a proposal is a deliberate
human act through the CLI or an MCP client.

## Writing your own

```python
from living_context.connectors.base import ConnectorResult, claim, packet, require, source_kind

class LinearConnector:
    name = "linear"
    description = "Read Linear issues as observations"
    required_config = ("team",)
    example = {"team": "ENG", "kind": "document"}

    def fetch(self, config, cursor, root=None):
        require(config, *self.required_config)
        kind = source_kind(config, "document")
        rows = my_client.issues(team=config["team"], since=cursor)   # your transport
        return ConnectorResult(
            packets=[
                packet(
                    ref=f"linear/{row['identifier']}",
                    kind=kind,
                    actor=row["creator"],
                    observed_at=row["updatedAt"],
                    entities=[{"name": row["project"], "kind": "solution", "aliases": []}],
                    claims=[
                        claim(
                            entity=row["project"],
                            attribute="status",
                            value=row["state"],
                            excerpt=row["title"],
                            kind=kind,
                            actor=row["creator"],
                            locator=row["identifier"],
                        )
                    ],
                )
                for row in rows
            ],
            cursor=max((row["updatedAt"] for row in rows), default=cursor),
        )
```

Register it in `living_context/connectors/__init__.py` and it appears in
`lce connectors`, `lce pull`, and the review queue with no other changes.

**Keep the transport in one injectable function** — `github_issues.fetch_json` is
the pattern — so the connector is testable without a network.

Two rules for any connector:

1. **Choose the weakest honest `kind`.** A CRM field is a `document`, not a
   `measurement`. An invoice is a `transaction`. Getting this wrong is the one
   way a connector can corrupt the graph, because the kind sets the confidence
   ceiling.
2. **Never fabricate evidence.** If a row has no quotable content, put the
   field name and value in the excerpt. Provenance a reviewer cannot check is
   worse than none.

## Not built in, on purpose

Notion, Linear, Jira, Google Docs, Salesforce, and Intercom are all one small
connector each — but each needs OAuth, a live account to test against, and
ongoing API maintenance. The `filedrop` connector plus the write API cover them
today with an automation platform in between, and cover them without the engine
taking on credentials it has no business holding.

If you build one, the contract above is the whole surface.
