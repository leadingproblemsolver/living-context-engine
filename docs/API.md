# Read-Only HTTP API

## Authentication

`/health` and `/health/live` are public liveness probes. All other endpoints require `Authorization: Bearer <LCE_API_TOKEN>` when a token is configured. A token is mandatory when the server binds beyond loopback.

## Endpoints

```text
GET /health
GET /health/live
GET /health/ready
GET /api/status
GET /api/projects
GET /api/query?q=<text>&project=<id>&limit=20
GET /api/timeline?project=<id>&limit=100
```

Limits are bounded server-side: query results up to 100 and timeline results up to 500. Query text is truncated to 500 characters. Responses are JSON with `Cache-Control: no-store`.

## Examples

```bash
curl http://127.0.0.1:8790/health
curl -H "Authorization: Bearer $LCE_API_TOKEN" \
  "http://127.0.0.1:8790/api/query?q=deployment&project=demo&limit=20"
```

The API does not ingest, edit, or delete data. Use the CLI for all mutations.
