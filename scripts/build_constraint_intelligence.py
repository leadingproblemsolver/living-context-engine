#!/usr/bin/env python3
"""Compile discovered engineering pain into constraint intelligence.

The input is a JSON list of signal-like records. Records may come directly from
GitHub discovery or from manually enriched observations. The compiler keeps
constraint value separate from intervention value so a strong market signal does
not automatically become a public-comment target.

Uses only the Python standard library and never publishes externally.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConstraintMatch:
    constraint_id: str
    constraint_name: str
    match_score: int
    matched_terms: list[str]


@dataclass(frozen=True)
class IntelligenceRecord:
    signal_id: str
    source_platform: str
    repository: str
    number: int | None
    url: str
    title: str
    author: str
    observed_at: str
    production_evidence: int
    economic_consequence: int
    workaround_burden: int
    recurrence: int
    cross_system_generality: int
    buyer_proximity: int
    serviceability: int
    proof_feasibility: int
    urgency: int
    commodity_penalty: int
    solved_penalty: int
    weak_evidence_penalty: int
    constraint_value: int
    intervention_value: int
    intervention: str
    constraint_id: str
    constraint_name: str
    constraint_match_score: int
    constraint_terms: list[str]
    economic_chain: list[str]
    saturation_state: str
    reason: str


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not load {path}: {exc}") from exc


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def text_of(record: dict[str, Any]) -> str:
    chunks = [
        str(record.get("title", "")),
        str(record.get("body", "")),
        str(record.get("reason", "")),
        str(record.get("draft_angle", "")),
        str(record.get("symptom", "")),
        str(record.get("actual", "")),
        str(record.get("expected", "")),
        str(record.get("workaround", "")),
        str(record.get("impact", "")),
        str(record.get("environment", "")),
    ]
    return "\n".join(chunks).lower()


def signal_id(record: dict[str, Any], index: int) -> str:
    repository = str(record.get("repository", "unknown"))
    number = record.get("number")
    if number is not None:
        return f"github:{repository}#{number}"
    return str(record.get("signal_id") or f"signal:{index}")


def classify_constraint(record: dict[str, Any], taxonomy: dict[str, Any]) -> ConstraintMatch:
    text = text_of(record)
    best: tuple[int, dict[str, Any], list[str]] | None = None
    for constraint in taxonomy.get("constraints", []):
        keywords = [str(k).lower() for k in constraint.get("keywords", [])]
        matched = sorted({keyword for keyword in keywords if keyword in text})
        score = min(100, 18 * len(matched))
        if best is None or score > best[0]:
            best = (score, constraint, matched)
    if best is None or best[0] == 0:
        return ConstraintMatch("unclassified", "Unclassified", 0, [])
    return ConstraintMatch(
        str(best[1]["id"]),
        str(best[1]["name"]),
        best[0],
        best[2],
    )


def marker_score(text: str, weighted_markers: tuple[tuple[str, int], ...], cap: int) -> int:
    return min(cap, sum(weight for marker, weight in weighted_markers if marker in text))


def score_production(record: dict[str, Any], text: str) -> int:
    explicit = record.get("production")
    if explicit is True:
        return 100
    if explicit is False:
        return 20
    score = marker_score(text, (
        ("production", 35), ("enterprise", 20), ("self-hosted", 15),
        ("kubernetes", 15), ("queue mode", 15), ("customer", 10),
        ("workflow", 5), ("scheduled", 8), ("incident", 10),
    ), 100)
    return max(25, score)


def score_economic(record: dict[str, Any], text: str) -> int:
    score = marker_score(text, (
        ("data loss", 30), ("duplicate", 22), ("downtime", 25),
        ("customer", 15), ("revenue", 25), ("manual restart", 20),
        ("manual re-auth", 20), ("manual", 8), ("69 hours", 25),
        ("hours", 8), ("days", 12), ("missed", 15), ("lost", 15),
        ("unauthorized", 12), ("wrong user", 25), ("security", 25),
        ("rollback", 18), ("100000", 15), ("2000 workflows", 20),
    ), 100)
    if record.get("customer_visible") is True:
        score += 15
    return clamp(max(20, score))


def score_workaround(record: dict[str, Any], text: str) -> int:
    score = marker_score(text, (
        ("manual restart", 35), ("restart", 15), ("re-auth", 30),
        ("downgrade", 25), ("rollback", 25), ("workaround", 15),
        ("daily", 18), ("every day", 18), ("manually", 12),
        ("only a full", 25), ("no workaround", 30),
    ), 100)
    return max(15, score)


def score_recurrence(record: dict[str, Any], text: str) -> int:
    if isinstance(record.get("frequency"), int):
        return clamp(int(record["frequency"]) * 15, 10, 100)
    score = marker_score(text, (
        ("intermittent", 20), ("recurring", 30), ("consistently", 25),
        ("every", 15), ("daily", 25), ("multiple", 18), ("again", 10),
        ("months", 25), ("weeks", 15), ("60%", 25),
    ), 100)
    return max(15, score)


def score_buyer(record: dict[str, Any], text: str) -> int:
    score = marker_score(text, (
        ("enterprise", 25), ("production", 20), ("our team", 15),
        ("our instance", 12), ("our pod", 12), ("our workflow", 8),
        ("self-hosted", 10), ("kubernetes", 10), ("customer", 10),
    ), 100)
    author_role = str(record.get("author_role", "")).lower()
    if author_role in {"maintainer", "founder", "platform engineer", "sre", "devops", "automation engineer"}:
        score += 25
    return clamp(max(15, score))


def score_serviceability(record: dict[str, Any], text: str) -> int:
    score = 35
    score += marker_score(text, (
        ("reproduce", 12), ("logs", 10), ("trace", 10), ("debug", 8),
        ("workaround", 8), ("configuration", 6), ("request", 5),
        ("postgres", 8), ("redis", 8), ("webhook", 8), ("credential", 8),
    ), 45)
    if record.get("requires_platform_ownership") is True:
        score -= 30
    return clamp(score)


def score_proof(record: dict[str, Any], text: str) -> int:
    score = 25 + marker_score(text, (
        ("steps to reproduce", 20), ("reproduce", 12), ("minimal", 12),
        ("exact", 8), ("curl", 10), ("screenshot", 6), ("logs", 8),
        ("execution id", 10), ("debug info", 8), ("same credential", 8),
    ), 65)
    return clamp(score)


def score_urgency(record: dict[str, Any], text: str) -> int:
    score = marker_score(text, (
        ("production", 20), ("customer", 15), ("blocked", 15),
        ("data loss", 30), ("security", 25), ("manual restart", 15),
        ("cannot", 8), ("unusable", 15), ("indefinitely", 12),
    ), 100)
    return max(15, score)


def penalty(record: dict[str, Any], text: str) -> tuple[int, int, int]:
    commodity = 20 if any(m in text for m in ("known workaround", "documented solution", "configuration mistake")) else 0
    solved = 35 if any(m in text for m in ("fixed in", "merged pr", "resolved by", "already fixed")) else 0
    weak = 20 if any(m in text for m in ("no reproduction", "cannot reproduce", "maybe", "unclear")) else 0
    if record.get("resolved") is True:
        solved = max(solved, 35)
    return commodity, solved, weak


def constraint_value(scores: dict[str, int], penalties: tuple[int, int, int]) -> int:
    value = (
        0.18 * scores["production"]
        + 0.16 * scores["economic"]
        + 0.14 * scores["workaround"]
        + 0.12 * scores["recurrence"]
        + 0.12 * scores["generality"]
        + 0.10 * scores["buyer"]
        + 0.08 * scores["serviceability"]
        + 0.06 * scores["proof"]
        + 0.04 * scores["urgency"]
    )
    return clamp(round(value - sum(penalties)))


def intervention_value(record: dict[str, Any], constraint_score: int, value: int) -> tuple[int, str]:
    comments = int(record.get("comments", 0) or 0)
    saturated = bool(record.get("saturated")) or comments >= 12
    fix_in_progress = bool(record.get("fix_in_progress"))
    unresolved = record.get("unresolved", True) is not False
    has_gap = bool(record.get("contribution_gap", True))

    score = value
    if saturated:
        score -= 30
    if fix_in_progress:
        score -= 30
    if not unresolved:
        score -= 40
    if not has_gap:
        score -= 25
    if constraint_score == 0:
        score -= 10
    score = clamp(score)

    if score < 30:
        action = "corpus_only"
    elif score < 45:
        action = "watch"
    elif score < 60:
        action = "ask_diagnostic_question"
    elif score < 72:
        action = "precision_comment"
    elif score < 82:
        action = "build_reproduction"
    elif score < 90:
        action = "build_patch_or_diagnostic"
    else:
        action = "operator_assistance_or_offer"
    return score, action


def economic_chain(record: dict[str, Any], match: ConstraintMatch) -> list[str]:
    symptom = str(record.get("symptom") or record.get("title") or "technical failure")
    workaround = str(record.get("workaround") or "manual detection/recovery")
    return [
        symptom,
        f"constraint: {match.constraint_name}",
        str(record.get("operational_consequence") or "workflow outcome becomes unreliable"),
        str(record.get("economic_consequence") or "operator time, downtime, or customer impact"),
        f"current compensation: {workaround}",
    ]


def compile_record(record: dict[str, Any], taxonomy: dict[str, Any], index: int, generality: int) -> IntelligenceRecord:
    text = text_of(record)
    match = classify_constraint(record, taxonomy)
    scores = {
        "production": score_production(record, text),
        "economic": score_economic(record, text),
        "workaround": score_workaround(record, text),
        "recurrence": score_recurrence(record, text),
        "generality": generality,
        "buyer": score_buyer(record, text),
        "serviceability": score_serviceability(record, text),
        "proof": score_proof(record, text),
        "urgency": score_urgency(record, text),
    }
    penalties = penalty(record, text)
    value = constraint_value(scores, penalties)
    ivalue, action = intervention_value(record, match.match_score, value)
    observed_at = str(record.get("observed_at") or datetime.now(timezone.utc).isoformat())
    repository = str(record.get("repository", ""))
    number = record.get("number")
    reason = (
        f"constraint={match.constraint_id}:{match.match_score}; value={value}; "
        f"production={scores['production']}, economic={scores['economic']}, "
        f"workaround={scores['workaround']}, recurrence={scores['recurrence']}, "
        f"buyer={scores['buyer']}; intervention={action}:{ivalue}."
    )
    return IntelligenceRecord(
        signal_id=signal_id(record, index),
        source_platform=str(record.get("source_platform", "github")),
        repository=repository,
        number=int(number) if number is not None else None,
        url=str(record.get("url", "")),
        title=str(record.get("title", "")),
        author=str(record.get("author", "")),
        observed_at=observed_at,
        production_evidence=scores["production"],
        economic_consequence=scores["economic"],
        workaround_burden=scores["workaround"],
        recurrence=scores["recurrence"],
        cross_system_generality=scores["generality"],
        buyer_proximity=scores["buyer"],
        serviceability=scores["serviceability"],
        proof_feasibility=scores["proof"],
        urgency=scores["urgency"],
        commodity_penalty=penalties[0],
        solved_penalty=penalties[1],
        weak_evidence_penalty=penalties[2],
        constraint_value=value,
        intervention_value=ivalue,
        intervention=action,
        constraint_id=match.constraint_id,
        constraint_name=match.constraint_name,
        constraint_match_score=match.match_score,
        constraint_terms=match.matched_terms,
        economic_chain=economic_chain(record, match),
        saturation_state="emerging",
        reason=reason,
    )


def apply_constraint_states(records: list[IntelligenceRecord]) -> list[IntelligenceRecord]:
    by_constraint: dict[str, list[IntelligenceRecord]] = defaultdict(list)
    for record in records:
        by_constraint[record.constraint_id].append(record)

    result: list[IntelligenceRecord] = []
    for record in records:
        family = by_constraint[record.constraint_id]
        repos = {item.repository for item in family if item.repository}
        strong = [item for item in family if item.constraint_value >= 65]
        if record.constraint_id == "unclassified":
            state = "emerging"
        elif len(strong) >= 5 and len(repos) >= 2:
            state = "validating"
        elif len(strong) >= 3:
            state = "confirmed"
        else:
            state = "emerging"
        data = asdict(record)
        data["saturation_state"] = state
        result.append(IntelligenceRecord(**data))
    return result


def generality_map(raw: list[dict[str, Any]], taxonomy: dict[str, Any]) -> dict[str, int]:
    repos_by_constraint: dict[str, set[str]] = defaultdict(set)
    for record in raw:
        match = classify_constraint(record, taxonomy)
        repository = str(record.get("repository", ""))
        if repository:
            repos_by_constraint[match.constraint_id].add(repository)
    return {
        constraint_id: clamp(25 + 18 * max(0, len(repos) - 1), 25, 100)
        for constraint_id, repos in repos_by_constraint.items()
    }


def summarize_constraints(records: list[IntelligenceRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[IntelligenceRecord]] = defaultdict(list)
    for record in records:
        grouped[record.constraint_id].append(record)
    rows: list[dict[str, Any]] = []
    for cid, family in grouped.items():
        repos = sorted({item.repository for item in family if item.repository})
        actions = Counter(item.intervention for item in family)
        rows.append({
            "constraint_id": cid,
            "constraint_name": family[0].constraint_name,
            "signals": len(family),
            "repositories": repos,
            "repository_count": len(repos),
            "avg_constraint_value": round(sum(item.constraint_value for item in family) / len(family), 1),
            "max_constraint_value": max(item.constraint_value for item in family),
            "state": family[0].saturation_state,
            "interventions": dict(actions),
            "top_signals": [
                {"signal_id": item.signal_id, "title": item.title, "value": item.constraint_value, "intervention": item.intervention}
                for item in sorted(family, key=lambda x: (-x.constraint_value, -x.intervention_value))[:5]
            ],
        })
    return sorted(rows, key=lambda row: (-row["avg_constraint_value"], -row["signals"]))


def render_markdown(records: list[IntelligenceRecord], constraints: list[dict[str, Any]]) -> str:
    lines = [
        "# Constraint Intelligence Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "> Default public action is no comment. Constraint value and intervention value are intentionally independent.",
        "",
        "## Constraint leaderboard",
        "",
    ]
    for index, row in enumerate(constraints, 1):
        lines.extend([
            f"### {index}. {row['constraint_name']} — avg {row['avg_constraint_value']}/100",
            f"- State: `{row['state']}`",
            f"- Signals: {row['signals']} across {row['repository_count']} repositories",
            f"- Repositories: {', '.join(row['repositories']) or 'unknown'}",
            f"- Intervention mix: {row['interventions']}",
            "",
        ])
    lines.extend(["## Highest-leverage signals", ""])
    for record in sorted(records, key=lambda x: (-x.constraint_value, -x.intervention_value))[:30]:
        target = f"[{record.repository} #{record.number}]({record.url})" if record.url else record.signal_id
        lines.extend([
            f"### {target} — constraint {record.constraint_value}/100; intervention {record.intervention_value}/100",
            f"**{record.title}**",
            f"- Constraint: `{record.constraint_id}` / {record.constraint_name}",
            f"- State: `{record.saturation_state}`",
            f"- Recommended action: `{record.intervention}`",
            f"- Reason: {record.reason}",
            f"- Economic chain: {' -> '.join(record.economic_chain)}",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("artifacts/github-review-queue.json"))
    parser.add_argument("--taxonomy", type=Path, default=Path("config/constraint_taxonomy.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/constraint-intelligence.json"))
    parser.add_argument("--constraints", type=Path, default=Path("artifacts/constraint-leaderboard.json"))
    parser.add_argument("--markdown", type=Path, default=Path("artifacts/constraint-intelligence.md"))
    args = parser.parse_args()

    raw = load_json(args.input)
    taxonomy = load_json(args.taxonomy)
    if not isinstance(raw, list):
        raise SystemExit("Input must be a JSON list")

    gmap = generality_map(raw, taxonomy)
    compiled = [
        compile_record(record, taxonomy, index, gmap.get(classify_constraint(record, taxonomy).constraint_id, 25))
        for index, record in enumerate(raw, 1)
        if isinstance(record, dict)
    ]
    compiled = apply_constraint_states(compiled)
    constraints = summarize_constraints(compiled)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([asdict(item) for item in compiled], indent=2) + "\n", encoding="utf-8")
    args.constraints.write_text(json.dumps(constraints, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(compiled, constraints), encoding="utf-8")
    print(f"Compiled {len(compiled)} signals into {len(constraints)} constraint families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
