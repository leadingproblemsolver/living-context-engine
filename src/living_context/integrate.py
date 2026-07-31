from __future__ import annotations

import json
from pathlib import Path

from living_context.config import CONFIG_RELATIVE, DEFAULTS

OBSERVATION_README = """\
# Observations

Drop anything here that tells you something about reality: interview notes,
support threads, competitor pages, meeting notes, exported issues.

A worked example lives in `.lce/examples/first-observation.md` — copy it here to
watch the loop run.

Two things become **state**; everything else stays a searchable note.

## 1. Claim lines

```
@source interviews/2026-07-14-acme
@actor jane@acme.example
@date 2026-07-14
@kind interview
@entity segment Manufacturing Ops Managers

claim: primary_pain = compliance reporting risk [importance=0.9]
claim: buyer = Department Head
claim: blockers[] = procurement approval
claim: competitor Northwind / pricing = $1,200 per site per month [kind=public_source]
unknown: Will they pay more than $2k/month? [impact=0.9, blocks=pricing tier]
relation: Manufacturing Ops Managers -[blocked_by]-> procurement approval
```

- `@` directives set defaults for every line below them in the file.
- `claim: <entity> / <attribute> = <value>` — the entity part is optional when
  `@entity` is set.
- Attributes are **single-valued**. Writing a different value for the same
  attribute is how you tell the engine a belief changed. Suffix with `[]` when
  the attribute really is a set.
- `[key=value]` modifiers: `kind`, `actor`, `importance`, `impact`, `blocks`,
  `n` (how many independent observations this line stands for).
- `decision:`, `risk:`, and `blocker:` lines each create an entity with a
  `status` claim.

## 2. Observation packets

Any `.json` / `.jsonl` file here is read as an observation packet — the same
shape a model produces from `lce prompt extract`. Absorb them with:

```
lce absorb .lce/observations/packet.json
```

## Source kinds, weakest to strongest

`inference` · `assertion` · `third_party` · `public_source` · `document` ·
`interview` · `usage_data` · `measurement` · `transaction` · `experiment`

The kind you choose caps how confident the engine will ever be. No number of
people *saying* they would pay can reach the confidence of one of them paying.
"""

EXAMPLE_OBSERVATION = """\
# Sample observation. Copy this file into .lce/observations/ to try the loop.
# It lives outside the ingested sources on purpose: a new graph should start
# empty, not pre-seeded with beliefs nobody actually holds.

@source examples/first-interviews
@kind interview
@date 2026-07-20
@entity segment Manufacturing Ops Managers

claim: primary_pain = manual compliance reporting [importance=0.9, n=6]
claim: buyer = Department Head [importance=0.8, n=4]
claim: blockers[] = procurement approval [n=3]
unknown: Will a Department Head sign off without procurement? [impact=0.8, blocks=self-serve pricing]
unknown: What do they spend on compliance reporting today? [impact=0.9]

decision: start with the compliance report exporter [importance=0.7]
risk: the exporter is easy for an incumbent to copy
"""

REPO_GUIDE = """\
# Living Context in this repository

This repo keeps a machine-maintained model of what we currently believe, why we
believe it, and what to check next. It is not a document store.

## Daily use

```bash
lce ingest                       # read every configured source, diff, update state
lce delta                        # what changed and why
lce state                        # the current reality model
lce contradictions               # where the evidence disagrees with itself
lce actions --refresh            # ranked next validation actions
lce context "should we build X"  # a decision-scoped context pack
lce metric                       # uncertainty removed over time
```

## Adding an observation

Write it into `.lce/observations/` using the syntax in that folder's README, or
produce a packet with any assistant:

```bash
lce prompt extract --input notes/customer-call.md > /tmp/prompt.txt
# paste into an assistant, save the JSON reply
lce absorb /tmp/reply.json
```

With `ANTHROPIC_API_KEY` set, `lce ingest --llm notes/` does that round trip for
you.

## Rules that keep this useful

- Claims need evidence. A claim with no source is not recorded.
- Contradictions are kept, not resolved by whoever wrote last.
- Confidence is derived from evidence weight, source independence, and age —
  never typed in by hand.
"""

WORKFLOW = """\
name: living-context
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - name: Install the engine
        run: python -m pip install living-context-engine
      - name: Update state from sources
        run: lce ingest --json
      - name: Rank next actions
        run: lce actions --refresh --json
      - name: Build a decision pack
        run: |
          lce context "what changed, what is blocked, what should we verify next" \\
            --output artifacts/current-context.md
      - name: Report uncertainty
        run: lce metric --json
      - uses: actions/upload-artifact@v4
        with:
          name: living-context
          path: artifacts/
"""

GITIGNORE_ENTRIES = ("data/living-context.sqlite", "data/living-context.sqlite-*")


def _write(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return "kept"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "written"


def _update_gitignore(root: Path) -> str:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = [entry for entry in GITIGNORE_ENTRIES if entry not in existing]
    if not missing:
        return "kept"
    suffix = "" if existing.endswith("\n") or not existing else "\n"
    path.write_text(
        existing + suffix + "\n# Living Context Engine\n" + "\n".join(missing) + "\n",
        encoding="utf-8",
    )
    return "updated"


def initialise(root: Path, project: str, with_ci: bool = False, force: bool = False) -> dict:
    """Make an arbitrary repository ready to run the engine."""
    root = Path(root)
    config = dict(DEFAULTS)
    config["project"] = project
    results = {
        CONFIG_RELATIVE: _write(
            root / CONFIG_RELATIVE, json.dumps(config, indent=2) + "\n", force
        ),
        ".lce/observations/README.md": _write(
            root / ".lce/observations/README.md", OBSERVATION_README, force
        ),
        ".lce/examples/first-observation.md": _write(
            root / ".lce/examples/first-observation.md", EXAMPLE_OBSERVATION, force
        ),
        "LCE.md": _write(root / "LCE.md", REPO_GUIDE, force),
        ".gitignore": _update_gitignore(root),
    }
    if with_ci:
        results[".github/workflows/lce.yml"] = _write(
            root / ".github/workflows/lce.yml", WORKFLOW, force
        )
    return {
        "project": project,
        "root": str(root),
        "files": results,
        "next": [
            "lce ingest",
            "lce actions --refresh",
            'lce context "what should we verify next"',
        ],
    }


def doctor(root: Path, config, store) -> dict:
    """Report whether this checkout can actually run the loop."""
    from living_context import llm

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    check(
        "config",
        config.exists,
        f"{CONFIG_RELATIVE} present" if config.exists else f"no {CONFIG_RELATIVE}; run `lce init`",
    )

    found = []
    missing = []
    for source in config.sources:
        matches = sorted(Path(root).glob(source))
        (found if matches else missing).append(source)
    check(
        "sources",
        bool(found),
        f"resolved: {', '.join(found) or 'none'}"
        + (f"; missing: {', '.join(missing)}" if missing else ""),
    )

    writable = True
    try:
        store.path.parent.mkdir(parents=True, exist_ok=True)
        probe = store.path.parent / ".lce-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        writable = False
        check("database", False, f"cannot write to {store.path.parent}: {error}")
    if writable:
        check("database", True, f"writable at {store.path}")

    check(
        "model-assisted extraction",
        llm.available(),
        "anthropic SDK installed"
        if llm.available()
        else "optional; install with pip install 'living-context-engine[llm]'",
    )

    status = store.status()
    check(
        "state",
        status["state"]["claims"] > 0,
        f"{status['state']['claims']} claims, {status['state']['entities']} entities"
        if status["state"]["claims"]
        else "graph is empty; run `lce ingest`",
    )

    return {
        "ok": all(item["ok"] for item in checks if item["check"] != "model-assisted extraction"),
        "checks": checks,
    }
