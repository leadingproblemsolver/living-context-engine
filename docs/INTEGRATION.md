# Integrating the engine into a repository

## One-time setup

```bash
pip install living-context-engine
cd your-repo
lce init --profile customer-discovery --ci --connectors
lce doctor
```

`--profile` seeds the vocabulary and starter questions for a kind of work
(`lce profiles` lists them), `--ci` writes a GitHub Actions workflow, and
`--connectors` writes `.lce/connectors.json` plus a drop folder.

`lce init` writes:

| Path | Purpose |
| --- | --- |
| `.lce/config.json` | project id, source globs, decay, model defaults |
| `.lce/observations/README.md` | the line syntax, in the folder where it is used |
| `.lce/examples/first-observation.md` | a worked example to copy in |
| `LCE.md` | how this repo uses the engine |
| `.gitignore` | ignores the SQLite database |

Nothing is overwritten unless you pass `--force`, so it is safe to re-run.

## Configuration

```json
{
  "project": "your-repo",
  "sources": ["docs", ".lce/observations"],
  "half_life_days": 180,
  "model": "claude-opus-5",
  "effort": "high",
  "database": "data/living-context.sqlite"
}
```

- `profile` sets the vocabulary injected into extraction prompts — see
  [`ADOPTION.md`](ADOPTION.md) §13.
- `auto_apply` lists the origins applied without review (default
  `["parser","human"]`). Add `"connector"` once `lce review` shows it earning its
  keep.
- `sources` are globs relative to the repository root. Point them at wherever
  observations actually live — `docs/`, `research/`, `notes/`, an exported
  `support/` dump.
- `half_life_days` controls how fast belief decays with age. A belief never
  falls below half its stated confidence from age alone. Fast-moving markets
  want 60–90; stable technical facts want 365 or `0` to disable decay.
- `database` is relative to the root. Point several repositories at one shared
  path to keep a single graph across them; projects stay isolated inside it.

Every command also accepts `--project` and `--root`, so the config is a
convenience rather than a requirement.

## Daily loop

```bash
lce ingest                  # all configured sources
lce ingest research/q3      # or a specific path
lce delta --since 2026-07-01
lce contradictions
lce actions --refresh --top 10
lce context "should we raise the price" --output artifacts/pricing.md
```

Bringing in the systems where evidence already lives:

```bash
lce pull                     # every configured connector, staged for review
lce review                   # accept, reject, or spot-check
lce identity --fix           # stage merges before the graph forks
lce digest --format slack --post-slack
```

Recording outcomes as work completes is what makes the metric mean anything:

```bash
lce resolve-unknown <id> --answer "median spend is $18k/yr, in the audit budget"
lce resolve-contradiction <id> --resolution "different sub-segments" --accept
lce action <id> --status done --result "8 interviews complete, see round-two.md"
```

`--accept` on a contradiction means both sides genuinely stand — different
populations, different contexts — rather than one having been settled.

## Continuous integration

`lce init --ci` writes a workflow that ingests, re-ranks, builds a context pack,
and uploads it as an artifact on every push. The useful variants:

```yaml
- run: lce ingest --json
- run: lce validate            # fails if the graph drifted from its provenance
- run: lce metric --json       # record the uncertainty trend over time
```

To gate a pull request on evidence rather than on files changed, read
`lce metric --json` and fail when uncertainty on the claims a change depends on
is above your threshold. The engine deliberately does not do this for you —
where that bar sits is a judgement about your risk, not a default.

## Using it from Python

```python
from pathlib import Path
from living_context.store import Store
from living_context.delta import apply_packet
from living_context.context import build_context
from living_context.actions import refresh_actions

store = Store(Path("."))
apply_packet(store, "my-project", packet)      # packet = the JSON shape in docs/OBSERVATIONS.md
refresh_actions(store, "my-project")
pack = build_context(store, "my-project", "should we build this")
store.close()
```

`Store` is a thin, synchronous SQLite wrapper with no global state; it is safe
to open one per request and close it.

## Reading the database directly

```sql
SELECT e.name, c.attribute, c.value, c.confidence
FROM claims c JOIN entities e ON e.entity_id = c.entity_id
WHERE c.project = 'your-repo' AND c.status = 'active'
ORDER BY c.confidence DESC;
```

Confidence in the table is the raw value; the CLI and API apply age decay on
read. Use `lce export --layer state` if you want the decayed numbers.

## Sharing state across a team

The database is a single file. Options, in increasing order of coordination:

1. Commit it. Works for small teams; merge conflicts on a binary are the cost.
2. Keep it out of git and rebuild it in CI from committed observations. The graph
   is fully derivable from its sources, so this is reproducible — with the
   caveat that resolutions recorded by hand (`resolve-unknown`,
   `resolve-contradiction`, action status) live only in the database. Commit
   those as observation files if you rebuild.
3. Run `lce serve` against a shared copy and read over HTTP.

## HTTP

```bash
lce serve --host 127.0.0.1 --port 8790
```

Loopback needs no token. Binding anywhere else requires `LCE_API_TOKEN` and the
server refuses to start without it. CORS is disabled unless one exact
`LCE_CORS_ORIGIN` is configured. The service is read-only: every mutation goes
through the CLI. See [`API.md`](API.md).
