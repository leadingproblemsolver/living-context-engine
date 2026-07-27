# Integration

Use `lce ingest <path> --project <id>` in local workflows or CI after meaningful project updates. Consumers can read JSON/CSV exports, query the SQLite file, or call the read-only API.

Recommended repository hook:

```bash
lce --root . ingest docs --project "$REPOSITORY_NAME"
lce --root . pack "current decisions blockers and next actions" --project "$REPOSITORY_NAME" --output artifacts/current-context.md
```

## HTTP security

Loopback access works without a token. Binding to `0.0.0.0`, a container network, or a public interface requires `LCE_API_TOKEN`; clients send `Authorization: Bearer <token>`. CORS is disabled unless one exact `LCE_CORS_ORIGIN` is configured.
