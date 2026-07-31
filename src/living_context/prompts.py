from __future__ import annotations

import json

from living_context.context import build_context, citations, render_markdown
from living_context.observe import OBSERVATION_SCHEMA
from living_context.store import Store

MAX_INPUT_CHARS = 120_000

EXTRACTION_RULES = """\
Rules:
1. Record state, not content. Never summarise the document. Say what is now
   believed to be true about a named thing, and what supports it.
2. Every claim needs at least one piece of evidence quoting or closely
   paraphrasing the source. A claim you cannot support does not go in `claims` —
   put it in `unknowns` as a question instead.
3. Pick the weakest source kind that honestly describes the evidence. Someone
   saying they would pay is an `interview` or an `assertion`, never a
   `transaction`. Only observed behaviour counts as `experiment`, `usage_data`,
   `measurement`, or `transaction`.
4. Reuse the existing entity names and attribute names listed below whenever the
   source is talking about the same thing. A new name for an existing thing
   splits the graph and hides the change.
5. Attributes are single-valued slots: one entity has one `buyer`, and a new
   value means the belief changed. If something is genuinely a set, suffix the
   attribute with `[]` (for example `blockers[]`).
6. Disagreement is signal. If the source contradicts something in the existing
   state below, still record the new claim — the engine keeps both and flags the
   conflict. Do not reconcile it yourself, and do not soften it.
7. Set `importance` by what a wrong answer would cost, not by how interesting it
   is.
8. Output only the JSON object. No prose, no code fence, no commentary."""


def _entity_vocabulary(store: Store, project: str, limit: int = 120) -> str:
    groups = store.state(project)
    if not groups:
        return "(the graph is empty — you are establishing the initial vocabulary)"
    lines = []
    for group in groups[:limit]:
        attributes = sorted({claim["attribute"] for claim in group["claims"]})
        lines.append(f"- {group['entity']} ({group['kind']}): {', '.join(attributes)}")
    return "\n".join(lines)


def _current_beliefs(store: Store, project: str, limit: int = 80) -> str:
    lines = []
    for group in store.state(project):
        for claim in group["claims"]:
            lines.append(
                f"- {group['entity']}.{claim['attribute']} = {claim['value']} "
                f"(confidence {claim['effective_confidence']:.2f}, "
                f"{claim['evidence_count']} evidence)"
            )
    if not lines:
        return "(no beliefs recorded yet)"
    return "\n".join(lines[:limit])


def prompt_extract(store: Store, project: str, text: str = "", source_ref: str = "") -> str:
    body = (text or "").strip()
    truncated = len(body) > MAX_INPUT_CHARS
    if truncated:
        body = body[:MAX_INPUT_CHARS]
    source_block = (
        f"Source reference to record: {source_ref}\n" if source_ref else ""
    )
    material = (
        f"<source_material>\n{body}\n</source_material>"
        if body
        else "<source_material>\nPASTE THE RAW SOURCE HERE (interview notes, transcript, "
        "competitor page, support thread, issue, meeting notes).\n</source_material>"
    )
    warning = (
        "\nNOTE: the source material was truncated to fit. Extract from what is present "
        "and add an unknown recording that the tail was not read.\n"
        if truncated
        else ""
    )
    return f"""\
You are converting a raw observation into a state update for a Living Context
Engine. The engine stores entities, claims, evidence, and confidence — not
documents.

{source_block}
Existing entities and attributes in this project (reuse these names):
{_entity_vocabulary(store, project)}

Current beliefs (you may contradict them; the engine records the conflict):
{_current_beliefs(store, project)}

{EXTRACTION_RULES}
{warning}
Return JSON matching exactly this schema:
{json.dumps(OBSERVATION_SCHEMA, indent=2)}

{material}
"""


def prompt_interview_guide(store: Store, project: str, count: int = 10) -> str:
    unknowns = store.unknowns(project, "open")[:count]
    if not unknowns:
        listing = "(no open unknowns — ingest more observations first)"
    else:
        listing = "\n".join(
            f"- [{row['unknown_id']}] {row['question']} (impact {row['impact']:.2f})"
            + (f" — blocks: {row['blocks_decision']}" if row["blocks_decision"] else "")
            for row in unknowns
        )
    weak = []
    for group in store.state(project):
        for claim in group["claims"]:
            if claim["effective_confidence"] < 0.6 and claim["importance"] >= 0.4:
                weak.append(
                    f"- {group['entity']}.{claim['attribute']} = {claim['value']} "
                    f"(confidence {claim['effective_confidence']:.2f})"
                )
    weak_block = "\n".join(weak[:20]) or "(none)"

    return f"""\
Write a research guide that would close the following open uncertainties for the
project "{project}".

Open questions, highest impact first:
{listing}

Weakly-held beliefs that need testing:
{weak_block}

Produce:
1. A screening definition: who must be in the room for the answers to count,
   and who would produce misleading answers.
2. 8-12 questions, ordered so the easy rapport questions come first and the
   uncomfortable ones come once trust exists. For each question, name the
   unknown id or belief it is designed to move.
3. For every question about money, switching, or future behaviour, rewrite it as
   a question about the past or about an observable artifact. "Would you pay
   $500/month?" is worthless; "What did you spend on this last quarter, and what
   line item did it come out of?" is evidence.
4. A falsification note: for the two or three most load-bearing beliefs above,
   state the specific answer that would prove them wrong. If no answer could,
   say so — the belief is not testable by interview and needs an experiment.
5. A capture template: the exact `claim:` lines to write down after each
   session, using the engine's syntax
   `claim: <entity> / <attribute> = <value> [kind=interview, actor=<who>]`.
"""


def prompt_adjudicate(store: Store, project: str, contradiction_id: str = "") -> str:
    rows = store.contradictions(project, "open")
    if contradiction_id:
        rows = [row for row in rows if row["contradiction_id"] == contradiction_id]
    if not rows:
        return "No open contradictions to adjudicate.\n"

    blocks = []
    for row in rows[:10]:
        details = []
        for side in ("claim_a", "claim_b"):
            claim = store.get_claim(row[side])
            if claim is None:
                continue
            evidence = store.evidence_for(claim["claim_id"])
            details.append(
                f"  Value: {claim['value']}\n"
                f"  Confidence: {claim['confidence']:.2f} "
                f"({len(evidence)} evidence, first seen {claim['first_seen_at']}, "
                f"last {claim['last_seen_at']})\n"
                f"  Evidence:\n"
                + "\n".join(
                    f"    - [{item['kind']}"
                    + (f" ×{item['count']}" if item["count"] > 1 else "")
                    + f"] {item['actor'] or 'unattributed'} @ {item['source']} "
                    f"— {item['excerpt'][:200]}"
                    for item in citations(evidence, limit=6)
                )
            )
        blocks.append(
            f"### {row['contradiction_id']} — {row.get('entity_name') or row['entity_id']}"
            f".{row['attribute']} (severity {row['severity']:.2f})\n"
            + "\n\n  vs\n\n".join(details)
        )

    return f"""\
Two beliefs in the project "{project}" disagree. Your job is not to pick the
more plausible one. It is to work out what kind of disagreement this is and what
observation would settle it.

{(chr(10) * 2).join(blocks)}

For each contradiction, answer in this order:

1. Type of conflict. Exactly one of:
   - measurement (both true, measured differently)
   - population (both true, different segments or contexts)
   - temporal (both true, the world changed between them)
   - stated-vs-revealed (one side reports intent, the other observes behaviour)
   - authority (one source is simply better positioned to know)
   - genuine (they cannot both be true)
2. What the conflict itself tells you. A stated-vs-revealed split usually means
   the question is wrong, not the answer.
3. The single cheapest observation that would retire one side. Name the method,
   the sample, and what result would count as decisive.
4. Whether to keep both beliefs alive in the meantime, and what decision each
   one would imply. If a decision is the same under both, say so — the conflict
   is not worth resolving yet.
5. The command to record the outcome, once observed:
   `lce resolve-contradiction <id> --resolution "<what settled it>"`
"""


def prompt_actions(store: Store, project: str, count: int = 10) -> str:
    actions = store.actions(project, status="proposed", limit=count)
    metric = store.uncertainty(project)
    if not actions:
        listing = "(no proposals — run `lce actions --refresh` first)"
    else:
        listing = "\n".join(
            f"{index}. {row['title']}\n"
            f"   kind={row['kind']} priority={row['priority']:.3f} "
            f"gain=+{row['expected_confidence_gain']:.2f} effort={row['effort_days']:g}d\n"
            f"   why: {row['rationale']}"
            for index, row in enumerate(actions, 1)
        )

    return f"""\
The engine has ranked these validation actions for "{project}" by expected
uncertainty removed per unit of effort.

Current uncertainty: {metric['uncertainty']:.2f} across
{metric['claims_active']} active claims, {metric['unknowns_open']} open
unknowns, {metric['contradictions_open']} open contradictions.

{listing}

Turn this into a plan someone can start tomorrow:

1. Sequence the work for the next two weeks. Put actions whose result changes
   what the later actions should be at the front, even if they rank lower.
2. Merge actions that one conversation or one instrument could answer together.
   Ten interviews that each test one belief is wasteful; ten interviews that
   test six beliefs is a week's work.
3. Flag any action whose method cannot actually settle its target — asking
   people about future spending, for instance — and replace it with one that can.
4. For each item, state the stopping rule: what result means "done, belief
   updated" versus "inconclusive, escalate".
5. Name what you are deliberately not doing and why it can wait.
6. End with the specific `lce` commands to record the results as they land.
"""


def prompt_decision_brief(store: Store, project: str, task: str, limit: int = 25) -> str:
    pack = build_context(store, project, task, limit=limit)
    return f"""\
Decide the question below using only the state in the context pack. The pack was
generated from evidence in the project's graph; every claim carries its own
confidence and provenance.

Question: {task}

{render_markdown(pack)}

Answer in this shape:

1. Recommendation, in one sentence, with the confidence you would attach to it.
2. The two or three beliefs the recommendation actually rests on. For each, give
   its current confidence and say plainly what happens to the recommendation if
   it is wrong.
3. Whether the evidence supports deciding now at all. If the load-bearing
   beliefs sit below 0.6, or an open contradiction touches one of them, say the
   honest answer is "not yet" and name what would change that.
4. What you would do differently if you had to commit today anyway — the
   reversible version of the decision.
5. The one observation that would most change this recommendation.

Do not use knowledge outside the pack. If the pack does not contain what you
need, say which claim is missing rather than filling the gap.
"""


def prompt_review_delta(store: Store, project: str, limit: int = 30) -> str:
    transitions = store.transitions(project, limit=limit)
    if not transitions:
        return "No recorded transitions to review.\n"
    listing = "\n".join(
        f"- [{row['transition_type']}] {row.get('entity_name') or row['entity_id']}"
        f".{row['attribute']}: {row['from_value'] or '∅'} → {row['to_value']} "
        f"({row['from_confidence']:.2f} → {row['to_confidence']:.2f})\n"
        f"  rationale: {row['rationale']}"
        for row in transitions
    )
    return f"""\
Audit the recent state changes in "{project}" for over-confidence and drift.

{listing}

For each transition, check:
1. Does the evidence described actually support the size of the confidence move,
   or is repetition being counted as corroboration?
2. Is a `revised` transition a real update, or did a louder recent source
   overwrite a better-evidenced older one?
3. Is a `contested` pair actually two different questions wearing the same
   attribute name?
4. Did any belief change without a corresponding change in the world — a
   rewording, a re-reading of the same source, a renamed entity?

Report only the transitions that fail a check, with the specific correction. If
they all hold up, say so in one line and stop.
"""


PROMPTS = {
    "extract": (
        "Turn raw source material into an observation packet the engine can absorb",
        lambda store, project, args: prompt_extract(
            store, project, text=args.get("text", ""), source_ref=args.get("source_ref", "")
        ),
    ),
    "interview-guide": (
        "Generate a research guide targeting the current open unknowns",
        lambda store, project, args: prompt_interview_guide(
            store, project, count=int(args.get("count", 10))
        ),
    ),
    "adjudicate": (
        "Work out what would settle an open contradiction",
        lambda store, project, args: prompt_adjudicate(
            store, project, contradiction_id=args.get("id", "")
        ),
    ),
    "actions": (
        "Turn ranked validation actions into a sequenced two-week plan",
        lambda store, project, args: prompt_actions(
            store, project, count=int(args.get("count", 10))
        ),
    ),
    "decision-brief": (
        "Answer a specific decision from the task-scoped context pack",
        lambda store, project, args: prompt_decision_brief(
            store,
            project,
            task=args.get("task") or "Should we proceed?",
            limit=int(args.get("limit", 25)),
        ),
    ),
    "review-delta": (
        "Audit recent state changes for over-confidence and drift",
        lambda store, project, args: prompt_review_delta(
            store, project, limit=int(args.get("limit", 30))
        ),
    ),
}


def render_prompt(name: str, store: Store, project: str, args: dict | None = None) -> str:
    if name not in PROMPTS:
        raise ValueError(
            f"unknown prompt: {name}. Available: {', '.join(sorted(PROMPTS))}"
        )
    return PROMPTS[name][1](store, project, args or {})


def list_prompts() -> list[dict]:
    return [
        {"name": name, "description": description}
        for name, (description, _) in sorted(PROMPTS.items())
    ]
