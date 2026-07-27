# Deployability and Distribution

## Distribution form

The primary distribution is a dependency-free Python wheel and `lce` console command. Persistent state is one SQLite database under the chosen `--root`.

## Build and install

```bash
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
python -m pip install --no-index --no-deps dist/living_context_engine-*.whl
lce --root /var/lib/lce validate
```

## Service deployment

Loopback access is unauthenticated. Binding to a container or non-loopback interface requires `LCE_API_TOKEN`; clients provide `Authorization: Bearer <token>`. Configure one exact `LCE_CORS_ORIGIN` only when browser access is required.

```bash
cp .env.example .env
# replace LCE_API_TOKEN
docker compose up --build
```

Persist `/app/data`. Back up the SQLite database before upgrades or destructive project deletion. Rollback uses the previous wheel/container plus the compatible database backup.

## Activation

Activation is complete when a real project corpus is ingested and a source-linked context pack helps an operator reopen a decision, blocker, risk, or next action without searching the original corpus manually.

## Remaining external proof

Production throughput, multi-user tenancy, access-policy integration, backup restoration, and long-term retrieval usefulness require live deployment evidence. The built-in API intentionally has no write endpoints.
