# Read-Only HTTP API

```bash
lce serve --host 127.0.0.1 --port 8790
```

One write endpoint, which **stages** rather than applies. Ingestion, acceptance,
resolution, and deletion are CLI-only.

`GET /` serves an HTML dashboard of the current digest.

## Authentication

`/health` and `/health/live` are public liveness probes. Every other endpoint
requires `Authorization: Bearer <LCE_API_TOKEN>` when a token is configured, and
a token is mandatory when the server binds beyond loopback — it refuses to start
otherwise.

## Endpoints

### Observation layer

```text
GET /health
GET /health/live
GET /health/ready
GET /api/status
GET /api/projects
GET /api/query?q=<text>&project=<id>&limit=20
GET /api/timeline?project=<id>&limit=100
```

### State layer

All of these require a project — from `?project=`, or from `.lce/config.json`
when the server was started in a configured repository. Without one they return
`400 {"error": "project_required"}`.

```text
GET /api/state?project=<id>&entity=<name-or-id>
GET /api/entities?project=<id>&kind=<kind>
GET /api/delta?project=<id>&since=<iso8601>&limit=50
GET /api/contradictions?project=<id>&status=open
GET /api/unknowns?project=<id>&status=open
GET /api/actions?project=<id>&status=proposed&limit=20
GET /api/metric?project=<id>&limit=20
GET /api/context?project=<id>&task=<question>&limit=25
GET /api/decisions?project=<id>
GET /api/proposals?project=<id>&status=pending&limit=50
GET /api/digest?project=<id>&since=<iso8601>
```

### Write

```text
POST /api/observations
```

Requires `LCE_API_WRITE_TOKEN`, which must differ from `LCE_API_TOKEN` — the
server refuses to start otherwise, so a read token can never propose state. Send
`Idempotency-Key` to make retries safe. Body is one packet, `{"packets": [...]}`,
or a bare array; limit 5 MB. Claims without evidence are rejected and named.

Everything it accepts is **staged for review**. See
[`CONNECTORS.md`](CONNECTORS.md) for the full contract.

`/api/context` is the interesting one: it runs the same task-scoped assembly as
`lce context` and returns the pack as JSON — entities and claims with citations,
recent transitions, contradictions and unknowns in scope, ranked actions, and
the uncertainty summary.

`/api/state` and `/api/metric` apply the configured age decay, so the numbers
match the CLI.

## Limits

Query text is truncated to 500 characters and task text to 500. Result limits
are bounded server-side: query 100, timeline 500, delta 500, actions 200,
metric 200, context 100. Responses are JSON with `Cache-Control: no-store`.

## Examples

```bash
curl http://127.0.0.1:8790/health

curl -H "Authorization: Bearer $LCE_API_TOKEN" \
  "http://127.0.0.1:8790/api/state?project=demo"

curl -H "Authorization: Bearer $LCE_API_TOKEN" \
  --get --data-urlencode "task=should we raise the price" \
  "http://127.0.0.1:8790/api/context?project=demo"
```
