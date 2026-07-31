from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from living_context import actions as action_router
from living_context import integrate, prompts
from living_context.config import load_config, resolve_project
from living_context.context import build_context, write_context
from living_context.delta import apply_packet, apply_packets
from living_context.extract import extract_path, iter_sources, observed_at, read_source
from living_context.llm import LLMUnavailable
from living_context.models import confidence_from_evidence
from living_context.observe import load_packets, packet_from_text
from living_context.packs import build_pack
from living_context.server import serve
from living_context.store import Store

PACKET_SUFFIXES = {".json", ".jsonl"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lce",
        description=(
            "Living Context Engine — compile messy observations into a traceable model "
            "of what you believe, what changed, and what to verify next."
        ),
    )
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument("--project", help="project id (default: from .lce/config.json)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_command(name: str, **kwargs) -> argparse.ArgumentParser:
        """Every subcommand also takes --project, so flag order never matters."""
        created = subparsers.add_parser(name, **kwargs)
        created.add_argument("--project", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return created

    sub = SimpleNamespace(add_parser=add_command)

    init = sub.add_parser("init", help="scaffold the engine into this repository")
    init.add_argument("--ci", action="store_true", help="also write a GitHub Actions workflow")
    init.add_argument("--force", action="store_true", help="overwrite existing files")

    ingest = sub.add_parser("ingest", help="read sources, diff against state, record changes")
    ingest.add_argument("path", nargs="*", help="files or directories (default: configured sources)")
    ingest.add_argument("--llm", action="store_true", help="use the Anthropic SDK to extract state")
    ingest.add_argument("--model", help="model id for --llm")
    ingest.add_argument("--no-state", action="store_true", help="store observations only")
    ingest.add_argument("--json", action="store_true")

    absorb = sub.add_parser("absorb", help="apply an observation packet (JSON or JSONL)")
    absorb.add_argument("path")
    absorb.add_argument("--json", action="store_true")

    state = sub.add_parser("state", help="the current reality model")
    state.add_argument("--entity", help="restrict to one entity (name or id)")
    state.add_argument("--min-confidence", type=float, default=0.0)
    state.add_argument("--include-superseded", action="store_true")
    state.add_argument("--json", action="store_true")

    delta = sub.add_parser("delta", help="what changed, and why")
    delta.add_argument("--since", help="ISO-8601 lower bound")
    delta.add_argument("--limit", type=int, default=50)
    delta.add_argument("--json", action="store_true")

    contradictions = sub.add_parser("contradictions", help="where the evidence disagrees")
    contradictions.add_argument("--all", action="store_true", help="include resolved")
    contradictions.add_argument("--json", action="store_true")

    unknowns = sub.add_parser("unknowns", help="open questions, by impact")
    unknowns.add_argument("--all", action="store_true", help="include resolved")
    unknowns.add_argument("--json", action="store_true")

    actions_cmd = sub.add_parser("actions", help="ranked next validation actions")
    actions_cmd.add_argument("--refresh", action="store_true", help="regenerate proposals")
    actions_cmd.add_argument("--top", type=int, default=10)
    actions_cmd.add_argument("--status", default="proposed")
    actions_cmd.add_argument("--json", action="store_true")

    context = sub.add_parser("context", help="build a decision-scoped context pack")
    context.add_argument("task")
    context.add_argument("--output", default="artifacts/context.md")
    context.add_argument("--limit", type=int, default=25)
    context.add_argument("--stdout", action="store_true", help="print instead of writing files")

    prompt = sub.add_parser("prompt", help="render a ready-to-use prompt with live state")
    prompt.add_argument("name")
    prompt.add_argument("--input", help="source file to embed (for extract)")
    prompt.add_argument("--task", help="decision question (for decision-brief)")
    prompt.add_argument("--id", dest="target_id", help="contradiction id (for adjudicate)")
    prompt.add_argument("--count", type=int, default=10)
    prompt.add_argument("--limit", type=int, default=25)
    prompt.add_argument("--output", help="write to a file instead of stdout")
    sub.add_parser("prompts", help="list available prompts")

    metric = sub.add_parser("metric", help="uncertainty, and how fast it is falling")
    metric.add_argument("--limit", type=int, default=20)
    metric.add_argument("--snapshot", action="store_true", help="record a new snapshot")
    metric.add_argument("--json", action="store_true")

    entities = sub.add_parser("entities", help="list entities")
    entities.add_argument("--kind")
    entities.add_argument("--json", action="store_true")

    resolve_unknown = sub.add_parser("resolve-unknown", help="answer an open question")
    resolve_unknown.add_argument("unknown_id")
    resolve_unknown.add_argument("--answer", required=True)
    resolve_unknown.add_argument("--drop", action="store_true", help="mark it no longer relevant")

    resolve_contradiction = sub.add_parser(
        "resolve-contradiction", help="record what settled a conflict"
    )
    resolve_contradiction.add_argument("contradiction_id")
    resolve_contradiction.add_argument("--resolution", required=True)
    resolve_contradiction.add_argument(
        "--accept", action="store_true", help="both sides stand (different contexts)"
    )

    complete = sub.add_parser("action", help="update an action's status")
    complete.add_argument("action_id")
    complete.add_argument(
        "--status", default="done", choices=["proposed", "in_progress", "done", "dropped"]
    )
    complete.add_argument("--result", default="")

    query = sub.add_parser("query", help="search raw observation records")
    query.add_argument("text")
    query.add_argument("--kind", action="append")
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--json", action="store_true")

    timeline = sub.add_parser("timeline", help="raw observation records in time order")
    timeline.add_argument("--limit", type=int, default=100)
    timeline.add_argument("--json", action="store_true")

    pack = sub.add_parser("pack", help="source-linked retrieval pack (observation layer)")
    pack.add_argument("text")
    pack.add_argument("--output", default="artifacts/context-pack.md")
    pack.add_argument("--limit", type=int, default=30)

    export = sub.add_parser("export", help="export the graph or the observation records")
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=["json", "csv"], default="json")
    export.add_argument("--layer", choices=["state", "records"], default="state")

    server = sub.add_parser("serve", help="read-only HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8790)

    sub.add_parser("status", help="database counts")
    sub.add_parser("projects", help="projects in this database")
    sub.add_parser("doctor", help="check that this checkout can run the loop")
    delete_project = sub.add_parser("delete-project", help="destructive: remove a project")
    delete_project.add_argument("target_project")
    delete_project.add_argument("--yes", action="store_true")
    sub.add_parser("validate", help="verify the repository and the graph's invariants")
    return parser


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


def _packet_for_file(
    file_path: Path, reference: str, text: str, use_llm: bool, store, project, model
) -> list[dict]:
    if file_path.suffix.lower() in PACKET_SUFFIXES:
        packets = load_packets(file_path)
        return [
            packet
            for packet in packets
            if isinstance(packet, dict) and ("claims" in packet or "source" in packet)
        ]
    if use_llm:
        from living_context import llm

        prompt = prompts.prompt_extract(store, project, text=text, source_ref=reference)
        packet = llm.extract_packet(prompt, model=model or llm.DEFAULT_MODEL)
        packet.setdefault("source", {})
        packet["source"].setdefault("ref", reference)
        return [packet]
    packet = packet_from_text(
        text,
        source_ref=reference,
        observed_at=observed_at(file_path),
    )
    if not (packet["claims"] or packet["unknowns"] or packet["relationships"]):
        return []
    return [packet]


def command_ingest(args, store: Store, config, project: str) -> int:
    targets = args.path or config.sources
    resolved: list[Path] = []
    for target in targets:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = config.root / candidate
        if candidate.exists():
            resolved.append(candidate)
    if not resolved:
        raise ValueError(
            "no readable sources. Pass a path, or configure `sources` in .lce/config.json "
            "(run `lce init`)."
        )

    before = store.uncertainty(project, config.half_life_days)
    record_summary = {"sources": 0, "records": 0}
    packets: list[tuple[dict, str]] = []
    skipped: list[str] = []

    for target in resolved:
        counts = store.ingest(extract_path(target, project, config.root))
        record_summary["sources"] += counts["sources"]
        record_summary["records"] += counts["records"]
        if args.no_state:
            continue
        for file_path, reference in iter_sources(target):
            try:
                text, _ = read_source(file_path)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                skipped.append(f"{reference}: {error}")
                continue
            try:
                for packet in _packet_for_file(
                    file_path, reference, text, args.llm, store, project, args.model
                ):
                    packets.append((packet, reference))
            except ValueError as error:
                skipped.append(f"{reference}: {error}")

    summary = {
        "project": project,
        "observations": record_summary,
        "skipped": skipped,
        "packets": 0,
        "entities_seen": 0,
        "claims_seen": 0,
        "evidence_added": 0,
        "transitions": [],
        "contradictions_opened": [],
        "unknowns_added": [],
        "transition_counts": {},
    }
    for packet, reference in packets:
        try:
            report = apply_packet(
                store, project, packet, config.half_life_days, source_ref=reference
            )
        except ValueError as error:
            skipped.append(f"{reference}: {error}")
            continue
        summary["packets"] += 1
        for key in ("entities_seen", "claims_seen", "evidence_added"):
            summary[key] += report[key]
        for key in ("transitions", "contradictions_opened", "unknowns_added"):
            summary[key].extend(report[key])
    for transition in summary["transitions"]:
        key = transition["transition_type"]
        summary["transition_counts"][key] = summary["transition_counts"].get(key, 0) + 1

    action_router.refresh_actions(store, project, config.half_life_days)
    after = store.snapshot_metric(project, config.half_life_days, note="ingest")
    summary["uncertainty_before"] = before["uncertainty"]
    summary["uncertainty_after"] = after["uncertainty"]
    summary["uncertainty_delta"] = round(after["uncertainty"] - before["uncertainty"], 4)

    if args.json:
        _emit(summary)
        return 0

    print(
        f"{record_summary['records']} observation records from "
        f"{record_summary['sources']} source(s); {summary['packets']} packet(s) applied."
    )
    print(
        f"state: {summary['entities_seen']} entities touched, "
        f"{summary['claims_seen']} claims seen, {summary['evidence_added']} new evidence."
    )
    if summary["transition_counts"]:
        counts = ", ".join(
            f"{count} {name}" for name, count in sorted(summary["transition_counts"].items())
        )
        print(f"changes: {counts}")
        for transition in summary["transitions"][:12]:
            arrow = (
                f"{transition['from_value']} -> {transition['to_value']}"
                if transition["from_value"]
                else transition["to_value"]
            )
            print(f"  [{transition['transition_type']}] {transition['attribute']}: {arrow}")
            print(f"      why: {transition['rationale']}")
    else:
        print("changes: none — nothing in the sources moved the model.")
    if summary["contradictions_opened"]:
        print(f"contradictions opened: {len(summary['contradictions_opened'])}")
        for row in summary["contradictions_opened"][:8]:
            print(f"  {row['attribute']}: {row['note']}")
    if summary["unknowns_added"]:
        print(f"new unknowns: {len(summary['unknowns_added'])}")
    if skipped:
        print(f"skipped {len(skipped)} source(s):")
        for line in skipped[:8]:
            print(f"  {line}")
    print(
        f"uncertainty: {before['uncertainty']:.2f} -> {after['uncertainty']:.2f} "
        f"({summary['uncertainty_delta']:+.2f})"
    )
    return 0


# ---------------------------------------------------------------------------
# readers
# ---------------------------------------------------------------------------


def command_state(args, store: Store, config, project: str) -> int:
    groups = store.state(
        project,
        entity=args.entity,
        half_life_days=config.half_life_days,
        include_superseded=args.include_superseded,
    )
    if args.min_confidence > 0:
        for group in groups:
            group["claims"] = [
                claim
                for claim in group["claims"]
                if claim["effective_confidence"] >= args.min_confidence
            ]
        groups = [group for group in groups if group["claims"]]
    if args.json:
        _emit(groups)
        return 0
    if not groups:
        print("No state yet. Run `lce ingest`.")
        return 0
    for group in groups:
        print(f"\n{group['entity']}  [{group['kind']}]")
        for claim in group["claims"]:
            marker = "" if claim["status"] == "active" else f" ({claim['status']})"
            stale = " ~ageing" if claim["staleness_factor"] < 0.8 else ""
            print(
                f"  {claim['attribute']:<24} {claim['value']}{marker}"
                f"   [conf {claim['effective_confidence']:.2f} · "
                f"{claim['evidence_count']} evidence{stale}]"
            )
    return 0


def command_delta(args, store: Store, config, project: str) -> int:
    rows = store.transitions(project, since=args.since, limit=args.limit)
    if args.json:
        _emit(rows)
        return 0
    if not rows:
        print("No recorded state changes.")
        return 0
    for row in rows:
        arrow = f"{row['from_value']} -> {row['to_value']}" if row["from_value"] else row["to_value"]
        print(
            f"{row['occurred_at']}  [{row['transition_type']}]  "
            f"{row.get('entity_name') or row['entity_id']}.{row['attribute']}"
        )
        print(f"    {arrow}   ({row['from_confidence']:.2f} -> {row['to_confidence']:.2f})")
        print(f"    why: {row['rationale']}")
    return 0


def command_contradictions(args, store: Store, config, project: str) -> int:
    rows = store.contradictions(
        project,
        status=None if args.all else "open",
        half_life_days=config.half_life_days,
    )
    if args.json:
        _emit(rows)
        return 0
    if not rows:
        print("No contradictions.")
        return 0
    for row in rows:
        print(
            f"{row['contradiction_id']}  [{row['status']}]  "
            f"{row.get('entity_name') or row['entity_id']}.{row['attribute']}  "
            f"severity {row['severity']:.2f}"
        )
        print(f"    A: {row['claim_a_value']}  (conf {row['claim_a_confidence'] or 0:.2f})")
        print(f"    B: {row['claim_b_value']}  (conf {row['claim_b_confidence'] or 0:.2f})")
        if row["resolution"]:
            print(f"    resolution: {row['resolution']}")
    return 0


def command_unknowns(args, store: Store, config, project: str) -> int:
    rows = store.unknowns(project, status=None if args.all else "open")
    if args.json:
        _emit(rows)
        return 0
    if not rows:
        print("No open unknowns.")
        return 0
    for row in rows:
        blocks = f"  blocks: {row['blocks_decision']}" if row["blocks_decision"] else ""
        print(f"{row['unknown_id']}  impact {row['impact']:.2f}  [{row['status']}]{blocks}")
        print(f"    {row['question']}")
    return 0


def command_actions(args, store: Store, config, project: str) -> int:
    if args.refresh:
        action_router.refresh_actions(store, project, config.half_life_days)
    rows = store.actions(project, status=args.status or None, limit=args.top)
    if args.json:
        _emit(rows)
        return 0
    if not rows:
        print("No actions. Run `lce actions --refresh` after ingesting.")
        return 0
    for index, row in enumerate(rows, 1):
        print(f"{index}. {row['title']}")
        print(
            f"    priority {row['priority']:.3f} · +{row['expected_confidence_gain']:.2f} "
            f"confidence · ~{row['effort_days']:g}d · {row['kind']} · {row['action_id']}"
        )
        print(f"    {row['rationale']}")
    return 0


def command_context(args, store: Store, config, project: str) -> int:
    pack = build_context(
        store, project, args.task, limit=args.limit, half_life_days=config.half_life_days
    )
    if args.stdout:
        from living_context.context import render_markdown

        print(render_markdown(pack))
        return 0
    output = Path(args.output)
    if not output.is_absolute():
        output = config.root / output
    _emit(write_context(pack, output))
    return 0


def command_prompt(args, store: Store, config, project: str) -> int:
    payload = {
        "count": args.count,
        "limit": args.limit,
        "task": args.task,
        "id": args.target_id,
    }
    if args.input:
        source = Path(args.input)
        if not source.is_absolute():
            source = config.root / source
        text, _ = read_source(source)
        payload["text"] = text
        payload["source_ref"] = source.name
    rendered = prompts.render_prompt(args.name, store, project, payload)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = config.root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)
    else:
        sys.stdout.write(rendered)
    return 0


def command_metric(args, store: Store, config, project: str) -> int:
    if args.snapshot:
        store.snapshot_metric(project, config.half_life_days, note="manual")
    current = store.uncertainty(project, config.half_life_days)
    history = store.metrics(project, limit=args.limit)
    rate = None
    if len(history) >= 2:
        from living_context.models import parse_timestamp

        newest, oldest = history[0], history[-1]
        hours = (
            parse_timestamp(newest["captured_at"]) - parse_timestamp(oldest["captured_at"])
        ).total_seconds() / 3600.0
        if hours > 0:
            rate = round((oldest["uncertainty"] - newest["uncertainty"]) / hours, 5)
    payload = {"current": current, "history": history, "uncertainty_removed_per_hour": rate}
    if args.json:
        _emit(payload)
        return 0
    print(f"uncertainty        {current['uncertainty']:.3f}")
    print(
        f"  unknowns {current['unknown_load']:.2f} · claims {current['claim_load']:.2f} "
        f"· contradictions {current['contradiction_load']:.2f}"
    )
    print(
        f"  {current['claims_active']} active claims, mean confidence "
        f"{current['mean_confidence']:.2f}"
    )
    print(
        f"  {current['unknowns_open']} open unknowns, "
        f"{current['contradictions_open']} open contradictions"
    )
    if rate is not None:
        print(f"uncertainty removed per hour: {rate:+.5f}")
    for row in history[:10]:
        print(f"  {row['captured_at']}  {row['uncertainty']:.3f}  ({row['note']})")
    return 0


def command_entities(args, store: Store, config, project: str) -> int:
    rows = store.entities(project, kind=args.kind)
    if args.json:
        _emit(rows)
        return 0
    for row in rows:
        aliases = f"  aka {', '.join(row['aliases'])}" if row["aliases"] else ""
        print(f"{row['entity_id']}  [{row['kind']:<11}] {row['name']}{aliases}")
    if not rows:
        print("No entities yet.")
    return 0


def command_export(args, store: Store, config, project: str) -> int:
    output = Path(args.output)
    if not output.is_absolute():
        output = config.root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.layer == "records":
        rows = store.timeline(project, 100000)
        fields = [
            "record_id", "project", "kind", "text", "source_path", "source_line",
            "source_hash", "observed_at", "status",
        ]
    else:
        rows = []
        for group in store.state(project, half_life_days=config.half_life_days):
            for claim in group["claims"]:
                rows.append(
                    {
                        "entity": group["entity"],
                        "entity_kind": group["kind"],
                        "attribute": claim["attribute"],
                        "value": claim["value"],
                        "confidence": claim["confidence"],
                        "effective_confidence": claim["effective_confidence"],
                        "importance": claim["importance"],
                        "evidence_count": claim["evidence_count"],
                        "status": claim["status"],
                        "first_seen_at": claim["first_seen_at"],
                        "last_seen_at": claim["last_seen_at"],
                        "claim_id": claim["claim_id"],
                    }
                )
        fields = [
            "entity", "entity_kind", "attribute", "value", "confidence",
            "effective_confidence", "importance", "evidence_count", "status",
            "first_seen_at", "last_seen_at", "claim_id",
        ]
    if args.format == "json":
        output.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    else:
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: row.get(key) for key in fields} for row in rows)
    print(output)
    return 0


def command_validate(args, store: Store, config, project: str) -> int:
    """Structural checks plus the invariants the graph is supposed to hold."""
    required = ["README.md", "pyproject.toml", "src/living_context/cli.py"]
    missing = [item for item in required if not (config.root / item).exists()]

    unsupported: list[str] = []
    unsupported.extend(
        f"claim {row['claim_id']} has no evidence"
        for row in store.conn.execute(
            """
            SELECT c.claim_id FROM claims c
            LEFT JOIN evidence e ON e.claim_id = c.claim_id
            WHERE e.evidence_id IS NULL
            """
        )
    )
    drifted: list[str] = []
    for row in store.conn.execute("SELECT claim_id, confidence FROM claims"):
        recomputed = confidence_from_evidence(store.evidence_for(row["claim_id"]))
        if abs(recomputed - row["confidence"]) > 0.001:
            drifted.append(
                f"claim {row['claim_id']} confidence {row['confidence']} != "
                f"recomputed {recomputed}"
            )
    orphans = [
        f"claim {row['claim_id']} references missing entity {row['entity_id']}"
        for row in store.conn.execute(
            """
            SELECT c.claim_id, c.entity_id FROM claims c
            LEFT JOIN entities e ON e.entity_id = c.entity_id
            WHERE e.entity_id IS NULL
            """
        )
    ]

    problems = missing + unsupported[:20] + drifted[:20] + orphans[:20]
    result = {
        "status": "ok" if not problems else "fail",
        "missing_files": missing,
        "claims_without_evidence": len(unsupported),
        "confidence_drift": len(drifted),
        "orphan_claims": len(orphans),
        "problems": problems,
        **store.status(),
    }
    _emit(result)
    return 0 if not problems else 1


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()

    try:
        config = load_config(root)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.command == "serve":
        serve(root, args.host, args.port, config.database)
        return 0

    if args.command == "init":
        project = args.project or config.project or root.name
        _emit(integrate.initialise(root, project, with_ci=args.ci, force=args.force))
        return 0

    store = Store(root, config.database)
    try:
        try:
            project = resolve_project(config, args.project)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        handlers = {
            "ingest": command_ingest,
            "absorb": None,
            "state": command_state,
            "delta": command_delta,
            "contradictions": command_contradictions,
            "unknowns": command_unknowns,
            "actions": command_actions,
            "context": command_context,
            "prompt": command_prompt,
            "metric": command_metric,
            "entities": command_entities,
            "export": command_export,
            "validate": command_validate,
        }

        if args.command == "absorb":
            path = Path(args.path)
            if not path.is_absolute():
                path = config.root / path
            packets = load_packets(path)
            summary = apply_packets(
                store, project, packets, config.half_life_days, source_ref=path.name
            )
            action_router.refresh_actions(store, project, config.half_life_days)
            summary["uncertainty"] = store.snapshot_metric(
                project, config.half_life_days, note="absorb"
            )
            _emit(summary)
            return 0

        handler = handlers.get(args.command)
        if handler is not None:
            return handler(args, store, config, project)

        if args.command == "prompts":
            _emit(prompts.list_prompts())
            return 0

        if args.command == "doctor":
            report = integrate.doctor(root, config, store)
            _emit(report)
            return 0 if report["ok"] else 1

        if args.command == "resolve-unknown":
            _emit(
                store.resolve_unknown(
                    args.unknown_id, args.answer, "dropped" if args.drop else "resolved"
                )
            )
            action_router.refresh_actions(store, project, config.half_life_days)
            store.snapshot_metric(project, config.half_life_days, note="resolve-unknown")
            return 0

        if args.command == "resolve-contradiction":
            _emit(
                store.resolve_contradiction(
                    args.contradiction_id,
                    args.resolution,
                    "accepted" if args.accept else "resolved",
                )
            )
            action_router.refresh_actions(store, project, config.half_life_days)
            store.snapshot_metric(project, config.half_life_days, note="resolve-contradiction")
            return 0

        if args.command == "action":
            _emit(store.update_action(args.action_id, args.status, args.result))
            return 0

        if args.command == "query":
            items = store.query(args.text, project, set(args.kind or []), args.limit)
            if args.json:
                _emit(items)
            elif items:
                print(
                    "\n".join(
                        f"[{item['score']:.2f}] {item['kind']} — {item['text']} "
                        f"({item['source_path']}:{item['source_line']})"
                        for item in items
                    )
                )
            else:
                print("No matching context.")
            return 0

        if args.command == "timeline":
            items = store.timeline(project, args.limit)
            if args.json:
                _emit(items)
            elif items:
                print(
                    "\n".join(
                        f"{item['observed_at']} | {item['kind']} | {item['text']} | "
                        f"{item['source_path']}:{item['source_line']}"
                        for item in items
                    )
                )
            else:
                print("No context ingested.")
            return 0

        if args.command == "pack":
            output = Path(args.output)
            if not output.is_absolute():
                output = config.root / output
            _emit(build_pack(store, args.text, output, project, args.limit))
            return 0

        if args.command == "status":
            _emit(store.status())
            return 0

        if args.command == "projects":
            _emit({"projects": store.projects()})
            return 0

        if args.command == "delete-project":
            if not args.yes:
                _emit(
                    {
                        "status": "blocked",
                        "reason": "pass --yes to confirm destructive deletion",
                    }
                )
                return 2
            _emit(store.delete_project(args.target_project))
            return 0
    except (ValueError, FileNotFoundError, LLMUnavailable) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        store.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
