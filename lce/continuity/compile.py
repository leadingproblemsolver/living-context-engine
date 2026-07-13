"""Deterministic compilation of a context packet into a source-linked,
decision-ready artifact. Given the same packet, output is identical except
for `created_at` -- there is no LLM involved in this path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from lce.continuity.packet import ContextPacket


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ArtifactMetadata:
    artifact_type: str
    mode: str
    topic: str
    created_at: str
    corpus_freshness: dict
    source_lineage: list[str]

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "mode": self.mode,
            "topic": self.topic,
            "created_at": self.created_at,
            "corpus_freshness": self.corpus_freshness,
            "source_lineage": self.source_lineage,
        }


@dataclass
class ArtifactSections:
    what_matters_now: list[str]
    decisions: list[dict]
    blockers: list[dict]
    next_actions: list[dict]
    assumptions_and_uncertainties: list[str]
    evidence: list[dict]
    next_operator_action: str

    def to_dict(self) -> dict:
        return {
            "what_matters_now": self.what_matters_now,
            "decisions": self.decisions,
            "blockers": self.blockers,
            "next_actions": self.next_actions,
            "assumptions_and_uncertainties": self.assumptions_and_uncertainties,
            "evidence": self.evidence,
            "next_operator_action": self.next_operator_action,
        }


@dataclass
class CompiledArtifact:
    metadata: ArtifactMetadata
    sections: ArtifactSections

    def to_dict(self) -> dict:
        return {"metadata": self.metadata.to_dict(), "sections": self.sections.to_dict()}


def _hit_summary(hit) -> dict:
    return {"content": hit.content, "source_path": hit.source_path, "score": hit.score, "reasons": hit.reasons}


def compile_artifact(packet: ContextPacket, *, artifact_type: str = "dossier", mode: str = "deterministic") -> CompiledArtifact:
    lineage = sorted(
        {
            h.source_path
            for h in (packet.decisions + packet.blockers + packet.next_actions + packet.assumptions + packet.questions + packet.evidence)
            if h.source_path
        }
    )

    what_matters_now = [h.content for h in (packet.decisions[:3] + packet.blockers[:3])]
    if not what_matters_now and packet.evidence:
        what_matters_now = [h.content for h in packet.evidence[:3]]

    assumptions_and_uncertainties = [h.content for h in packet.assumptions] + list(packet.uncertainties)

    if packet.blockers:
        next_operator_action = "Review the active blockers below and resolve or explicitly accept the highest-priority one."
    elif packet.next_actions:
        next_operator_action = "Review the next actions below and pick one to execute."
    elif not lineage:
        next_operator_action = f"No evidence exists yet for '{packet.query}'. Run `lce sync` on the relevant corpus and re-query."
    else:
        next_operator_action = "Review the evidence below; no blockers or next actions were found for this query."

    metadata = ArtifactMetadata(
        artifact_type=artifact_type,
        mode=mode,
        topic=packet.query,
        created_at=_now(),
        corpus_freshness=packet.freshness.to_dict(),
        source_lineage=lineage,
    )
    sections = ArtifactSections(
        what_matters_now=what_matters_now,
        decisions=[_hit_summary(h) for h in packet.decisions],
        blockers=[_hit_summary(h) for h in packet.blockers],
        next_actions=[_hit_summary(h) for h in packet.next_actions],
        assumptions_and_uncertainties=assumptions_and_uncertainties,
        evidence=[_hit_summary(h) for h in packet.evidence],
        next_operator_action=next_operator_action,
    )
    return CompiledArtifact(metadata=metadata, sections=sections)


def render_json(artifact: CompiledArtifact) -> dict:
    return artifact.to_dict()


def render_markdown(artifact: CompiledArtifact) -> str:
    m, s = artifact.metadata, artifact.sections
    lines = [
        f"# {m.artifact_type}: {m.topic}",
        "",
        f"- mode: `{m.mode}`",
        f"- created_at: `{m.created_at}`",
        f"- corpus stale: `{m.corpus_freshness.get('stale')}`" + (f" ({m.corpus_freshness.get('reason')})" if m.corpus_freshness.get("stale") else ""),
        "",
        "## What matters now",
    ]
    lines += [f"- {x}" for x in s.what_matters_now] or ["- (none)"]
    lines += ["", "## Decisions"]
    lines += [f"- {d['content']} (source: {d['source_path']})" for d in s.decisions] or ["- (none)"]
    lines += ["", "## Blockers"]
    lines += [f"- {d['content']} (source: {d['source_path']})" for d in s.blockers] or ["- (none)"]
    lines += ["", "## Next actions"]
    lines += [f"- {d['content']} (source: {d['source_path']})" for d in s.next_actions] or ["- (none)"]
    lines += ["", "## Assumptions and uncertainties"]
    lines += [f"- {x}" for x in s.assumptions_and_uncertainties] or ["- (none)"]
    lines += ["", "## Evidence"]
    lines += [f"- {d['content']} (source: {d['source_path']})" for d in s.evidence] or ["- (none)"]
    lines += ["", "## Next operator action", s.next_operator_action]
    lines += ["", "## Source lineage"]
    lines += [f"- {p}" for p in m.source_lineage] or ["- (none)"]
    return "\n".join(lines) + "\n"
