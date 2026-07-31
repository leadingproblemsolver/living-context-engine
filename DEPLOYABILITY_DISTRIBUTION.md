# Deployability and Distribution

## Distribution form

A dependency-free Python wheel and the `lce` console command. Persistent state is
one SQLite database under the chosen `--root`. Model-assisted extraction is the
only optional dependency, declared as the `llm` extra; everything else runs
offline with no account and no key.

## Build and install

```bash
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
python -m pip install --no-index --no-deps dist/living_context_engine-*.whl
lce --root /var/lib/lce --project ops validate
```

With model-assisted extraction:

```bash
python -m pip install 'living-context-engine[llm]'
export ANTHROPIC_API_KEY=...
lce ingest --llm notes/
```

## Integrating into another repository

```bash
cd target-repo
lce init --ci
```

Writes `.lce/config.json`, a syntax guide next to where observations live, a
worked example, `LCE.md`, a `.gitignore` entry for the database, and a GitHub
Actions workflow. Re-running is safe; nothing is overwritten without `--force`.
`lce doctor` reports whether the checkout can actually run the loop.

The graph is derivable from its sources, so a team can either commit the
database or rebuild it in CI from committed observations — with the caveat that
hand-recorded resolutions (`resolve-unknown`, `resolve-contradiction`, action
status) live only in the database and must be committed as observations if you
rebuild.

## Service deployment

Loopback access is unauthenticated. Binding to a container or non-loopback
interface requires `LCE_API_TOKEN`, and the server refuses to start without one.
Configure a single exact `LCE_CORS_ORIGIN` only when browser access is required.
The HTTP service is read-only across both layers; every mutation goes through
the CLI.

```bash
cp .env.example .env
# replace LCE_API_TOKEN
docker compose up --build
```

Persist `/app/data`. Back up the SQLite database before upgrades or destructive
project deletion. Rollback uses the previous wheel or container plus the
compatible database backup; v1 databases open and migrate forward, and the v1
observation layer is unchanged.

## Activation

Activation is complete when a real corpus has been ingested and the engine has
done three things an operator agrees with: named a belief that changed and why,
surfaced a contradiction they had been carrying without noticing, and proposed a
verification action they then actually ran.

## Remaining external proof

Extraction quality against a labelled corpus, model-assisted extraction accuracy,
whether the ranked actions shorten real decisions, production throughput,
multi-user tenancy, access-policy integration, and backup restoration all require
live evidence.
