from __future__ import annotations

# Adaptation is data, not a fork. A profile is the vocabulary and the starting
# questions for one kind of work; the engine's mechanics never change.

PROFILES: dict[str, dict] = {
    "customer-discovery": {
        "description": "Who has the problem, who buys, what they pay, what blocks them",
        "entity_kinds": ["segment", "company", "person", "problem", "competitor", "channel"],
        "attributes": {
            "segment": [
                "primary_pain",
                "trigger_event",
                "buyer",
                "decision_maker",
                "blockers[]",
                "current_workaround",
                "willingness_to_pay",
                "switching_cost",
            ],
            "competitor": ["pricing", "positioning", "segment_served", "onboarding", "weakness"],
            "channel": ["cost_per_lead", "conversion_rate", "cycle_length"],
        },
        "starter_unknowns": [
            ("Who exactly has this problem badly enough to pay for it?", 0.95, "who to build for"),
            ("What do they spend on it today, and out of which budget?", 0.9, "pricing"),
            ("Who signs, and what approval do they need?", 0.85, "sales motion"),
            ("What happens if they do nothing?", 0.8, "urgency"),
        ],
        "starter_decisions": [
            "Which segment do we build for first?",
            "What do we charge, and on what basis?",
            "Which channel do we test first?",
        ],
        "evidence_note": (
            "Interviews are the workhorse here and they cap at 0.85. Anything about "
            "money needs a `transaction` before you plan around it."
        ),
    },
    "product-decisions": {
        "description": "Whether to build a thing, and what the evidence says it should do",
        "entity_kinds": ["solution", "problem", "segment", "metric", "constraint", "experiment"],
        "attributes": {
            "solution": ["job_to_be_done", "activation_time", "differentiator", "adoption_rate", "failure_mode"],
            "metric": ["current_value", "target_value", "measured_by", "moved_by"],
            "constraint": ["status", "owner", "workaround"],
        },
        "starter_unknowns": [
            ("Which metric would this move, and by how much?", 0.9, "whether to build it"),
            ("What is the cheapest version that would tell us we are wrong?", 0.85, "scope"),
            ("What breaks if we ship it?", 0.7, "risk"),
        ],
        "starter_decisions": [
            "Do we build this, defer it, or kill it?",
            "What is in the first release?",
        ],
        "evidence_note": (
            "Usage data and experiments outrank opinion here. A stakeholder's "
            "preference is an `assertion` and caps at 0.60."
        ),
    },
    "security-posture": {
        "description": "What is actually true about exposure, controls, and open risk",
        "entity_kinds": ["constraint", "risk", "solution", "metric", "company"],
        "attributes": {
            "risk": ["status", "exposure", "likelihood", "mitigation", "owner"],
            "constraint": ["status", "control", "evidence_of_operation", "last_verified"],
            "metric": ["current_value", "target_value", "measured_by"],
        },
        "starter_unknowns": [
            ("Which controls are operating, as opposed to documented?", 0.95, "audit readiness"),
            ("Where is customer data actually stored, and who can reach it?", 0.95, "data policy"),
            ("What did the last incident change, and did it stick?", 0.8, "remediation"),
        ],
        "starter_decisions": [
            "Are we ready to claim this control is in place?",
            "What do we remediate first?",
        ],
        "evidence_note": (
            "A policy document is a `document` (0.75 ceiling). Only a `measurement` "
            "of the control running is real evidence — set half_life_days low, "
            "because a control verified last year is not verified."
        ),
    },
    "hiring": {
        "description": "What the role needs, and what the evidence about a candidate supports",
        "entity_kinds": ["person", "constraint", "metric", "problem"],
        "attributes": {
            "person": ["strength", "risk", "level", "motivation", "reference_signal"],
            "constraint": ["status", "must_have", "nice_to_have"],
        },
        "starter_unknowns": [
            ("What will this person own in ninety days?", 0.9, "the role definition"),
            ("What evidence would change our mind about the strongest candidate?", 0.85, "the offer"),
        ],
        "starter_decisions": ["Do we make an offer, and at what level?"],
        "evidence_note": (
            "An interview impression is an `interview` at best and often an "
            "`assertion`. A work sample is a `measurement`. The ceilings are the "
            "point: they stop a good conversation from outranking observed work."
        ),
    },
}

DEFAULT_PROFILE = "customer-discovery"


def get(name: str | None) -> dict | None:
    if not name:
        return None
    profile = PROFILES.get(name)
    if profile is None:
        raise ValueError(
            f"unknown profile '{name}'. Available: {', '.join(sorted(PROFILES))}"
        )
    return profile


def catalogue() -> list[dict]:
    return [
        {
            "name": name,
            "description": profile["description"],
            "entity_kinds": profile["entity_kinds"],
            "starter_decisions": profile["starter_decisions"],
        }
        for name, profile in sorted(PROFILES.items())
    ]


def vocabulary_block(name: str | None) -> str:
    """Suggested slots, injected into the extraction prompt.

    Two people running the same profile in different companies produce
    comparable graphs. That is what makes the tool replicable rather than
    bespoke to whoever set it up first.
    """
    profile = get(name)
    if profile is None:
        return ""
    lines = [f"Suggested vocabulary for the '{name}' profile — prefer these slots:"]
    for kind, attributes in profile["attributes"].items():
        lines.append(f"- {kind}: {', '.join(attributes)}")
    lines.append(profile["evidence_note"])
    return "\n".join(lines)


def starter_observation(name: str) -> str:
    profile = get(name)
    if profile is None:
        return ""
    lines = [
        f"# Open questions — {name}",
        "",
        "# The questions this kind of work always has to answer. Delete the ones",
        "# that do not apply, add the ones specific to you, then run `lce ingest`.",
        "",
        "@source starter/open-questions",
        "@kind inference",
        "",
    ]
    for question, impact, blocks in profile["starter_unknowns"]:
        lines.append(f"unknown: {question} [impact={impact}, blocks={blocks}]")
    lines.extend(["", "# Register the decisions these questions serve:", ""])
    for decision in profile["starter_decisions"]:
        lines.append(f'#   lce decision add "{decision}"')
    return "\n".join(lines) + "\n"
