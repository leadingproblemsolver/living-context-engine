from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from living_context import decisions as decision_board
from living_context.models import parse_timestamp
from living_context.store import Store

INTERESTING = ("revised", "contested", "established")
# A rate computed over a few seconds is noise dressed as a trend.
MIN_RATE_HOURS = 0.5



def build(
    store: Store,
    project: str,
    since: str | None = None,
    half_life_days: float = 180.0,
    action_limit: int = 3,
) -> dict:
    """The recurring artifact. Everything else in the engine serves this.

    If a team reads one thing a week, it is this: what changed, what is now in
    conflict, which decisions became answerable, and the next three moves.
    """
    transitions = store.transitions(project, since=since, limit=200)
    metric = store.uncertainty(project, half_life_days)
    history = store.metrics(project, limit=200)

    previous = None
    for row in history:
        if since and row["captured_at"] <= since:
            previous = row
            break
    if previous is None and len(history) > 1:
        previous = history[-1]

    trend = None
    rate = None
    if previous:
        trend = round(metric["uncertainty"] - previous["uncertainty"], 4)
        hours = (
            parse_timestamp(history[0]["captured_at"]) - parse_timestamp(previous["captured_at"])
        ).total_seconds() / 3600.0
        if hours >= MIN_RATE_HOURS:
            rate = round(-trend / hours, 5)

    board = decision_board.board(store, project, half_life_days)
    return {
        "project": project,
        "since": since,
        "uncertainty": metric,
        "uncertainty_change": trend,
        "uncertainty_removed_per_hour": rate,
        "changed": [row for row in transitions if row["transition_type"] in INTERESTING],
        "new_conflicts": [
            row
            for row in store.contradictions(project, "open", half_life_days)
            if not since or row["detected_at"] >= since
        ],
        "decidable": [row for row in board if row["readiness"] >= decision_board.DECIDABLE],
        "blocked": [
            row
            for row in board
            if row["status"] == "open" and row["readiness"] < decision_board.DECIDABLE
        ],
        "next_actions": store.actions(project, status="proposed", limit=action_limit),
        "pending_review": len(store.proposals(project, "pending", limit=1000)),
        "proposal_stats": store.proposal_stats(project),
    }


def _arrow(row: dict) -> str:
    return (
        f"{row['from_value']} → {row['to_value']}" if row["from_value"] else row["to_value"]
    )


def render_markdown(report: dict) -> str:
    metric = report["uncertainty"]
    change = (
        f" ({report['uncertainty_change']:+.2f})"
        if report["uncertainty_change"] is not None
        else ""
    )
    lines = [
        f"## Living Context — {report['project']}",
        "",
        f"**Uncertainty {metric['uncertainty']:.2f}{change}** · "
        f"{metric['claims_active']} active claims · mean confidence "
        f"{metric['mean_confidence']:.2f} · {metric['unknowns_open']} open questions · "
        f"{metric['contradictions_open']} open conflicts",
    ]
    if report["uncertainty_removed_per_hour"] is not None:
        lines.append(
            f"_Uncertainty removed per hour: {report['uncertainty_removed_per_hour']:+.4f}_"
        )

    lines.extend(["", f"### Beliefs that moved ({len(report['changed'])})"])
    if report["changed"]:
        for row in report["changed"][:10]:
            lines.append(
                f"- **{row['transition_type']}** "
                f"`{row.get('entity_name') or row['entity_id']}.{row['attribute']}` "
                f"{_arrow(row)}"
            )
            lines.append(f"  - {row['rationale']}")
    else:
        lines.append("- nothing moved")

    if report["new_conflicts"]:
        lines.extend(["", f"### New conflicts ({len(report['new_conflicts'])})"])
        for row in report["new_conflicts"][:8]:
            lines.append(
                f"- `{row.get('entity_name') or row['entity_id']}.{row['attribute']}`: "
                f"{row['note']} — severity {row['severity']:.2f} "
                f"(`lce prompt adjudicate --id {row['contradiction_id']}`)"
            )

    if report["decidable"]:
        lines.extend(["", f"### Ready to decide ({len(report['decidable'])})"])
        for row in report["decidable"]:
            lines.append(
                f"- **{row['question']}** — readiness {row['readiness']:.2f}"
                + (f", owner {row['owner']}" if row["owner"] else "")
            )
    if report["blocked"]:
        lines.extend(["", f"### Still blocked ({len(report['blocked'])})"])
        for row in report["blocked"][:8]:
            weakest = row["weakest_link"]
            detail = (
                f"weakest: {weakest['entity']}.{weakest['attribute']} at "
                f"{weakest['effective_confidence']:.2f}"
                if weakest
                else "no evidence linked yet"
            )
            lines.append(
                f"- **{row['question']}** — readiness {row['readiness']:.2f}; {detail}"
            )

    lines.extend(["", "### Do next"])
    if report["next_actions"]:
        for index, action in enumerate(report["next_actions"], 1):
            lines.append(
                f"{index}. {action['title']} — +{action['expected_confidence_gain']:.2f} "
                f"confidence, ~{action['effort_days']:g}d"
            )
    else:
        lines.append("- nothing queued; run `lce actions --refresh`")

    if report["pending_review"]:
        lines.extend(
            [
                "",
                f"### Waiting on you",
                f"{report['pending_review']} proposal(s) to review — `lce review`",
            ]
        )
    return "\n".join(lines) + "\n"


def render_slack(report: dict) -> dict:
    """Slack mrkdwn payload for an incoming webhook."""
    metric = report["uncertainty"]
    change = (
        f" ({report['uncertainty_change']:+.2f})"
        if report["uncertainty_change"] is not None
        else ""
    )
    parts = [
        f"*Living Context — {report['project']}*",
        f"Uncertainty *{metric['uncertainty']:.2f}*{change} · "
        f"{metric['claims_active']} claims · {metric['unknowns_open']} open questions · "
        f"{metric['contradictions_open']} conflicts",
    ]
    if report["changed"]:
        parts.append("*Beliefs that moved*")
        for row in report["changed"][:5]:
            parts.append(
                f"• _{row['transition_type']}_ `{row['attribute']}` {_arrow(row)}"
            )
    if report["new_conflicts"]:
        parts.append("*New conflicts*")
        for row in report["new_conflicts"][:3]:
            parts.append(f"• `{row['attribute']}`: {row['note']}")
    if report["decidable"]:
        parts.append("*Ready to decide*")
        for row in report["decidable"][:3]:
            parts.append(f"• {row['question']} ({row['readiness']:.2f})")
    if report["next_actions"]:
        parts.append("*Do next*")
        for action in report["next_actions"]:
            parts.append(f"• {action['title']}")
    if report["pending_review"]:
        parts.append(f"_{report['pending_review']} proposal(s) waiting for review_")
    return {"text": "\n".join(parts), "mrkdwn": True}


def post_slack(report: dict, webhook_url: str = "", timeout: float = 15.0) -> dict:
    url = webhook_url or os.environ.get("LCE_SLACK_WEBHOOK", "")
    if not url:
        raise ValueError(
            "no Slack webhook. Pass --slack-webhook or set LCE_SLACK_WEBHOOK."
        )
    if not url.startswith("https://"):
        raise ValueError("the Slack webhook must be an https URL")
    body = json.dumps(render_slack(report)).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"posted": True, "status": response.status}
    except urllib.error.HTTPError as error:
        raise ValueError(
            f"Slack rejected the digest ({error.code}): "
            f"{error.read().decode('utf-8', errors='replace')[:200]}"
        ) from error
    except urllib.error.URLError as error:
        raise ValueError(f"could not reach Slack: {error.reason}") from error


def render_html(report: dict) -> str:
    metric = report["uncertainty"]

    def rows(items, formatter):
        return "".join(f"<li>{formatter(item)}</li>" for item in items) or "<li>none</li>"

    def escape(text: object) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    return f"""<!doctype html>
<meta charset="utf-8"><title>Living Context — {escape(report['project'])}</title>
<style>
:root {{ color-scheme: light dark; --fg:#1a1a1a; --bg:#fbfaf7; --muted:#666; --line:#e3e0d8; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg:#e8e6e1; --bg:#17181a; --muted:#9a9a9a; --line:#2e3033; }}
}}
body {{ background:var(--bg); color:var(--fg); font:16px/1.55 ui-sans-serif,system-ui,sans-serif;
        max-width:52rem; margin:0 auto; padding:2rem 1.25rem; }}
h1 {{ font-size:1.4rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.05rem; margin:2rem 0 .5rem; border-bottom:1px solid var(--line); padding-bottom:.3rem; }}
.metric {{ font-size:2rem; font-weight:600; }}
.muted {{ color:var(--muted); font-size:.9rem; }}
ul {{ padding-left:1.1rem; }} li {{ margin:.35rem 0; }}
code {{ background:color-mix(in srgb, var(--fg) 8%, transparent); padding:.1em .35em; border-radius:3px; }}
.why {{ color:var(--muted); font-size:.9rem; }}
</style>
<h1>Living Context — {escape(report['project'])}</h1>
<p class="muted">what we believe, what changed, and what to check next</p>
<p class="metric">{metric['uncertainty']:.2f}
  <span class="muted">uncertainty{
    f" ({report['uncertainty_change']:+.2f})" if report['uncertainty_change'] is not None else ""
  }</span></p>
<p class="muted">{metric['claims_active']} active claims · mean confidence
  {metric['mean_confidence']:.2f} · {metric['unknowns_open']} open questions ·
  {metric['contradictions_open']} open conflicts · {report['pending_review']} awaiting review</p>

<h2>Beliefs that moved</h2>
<ul>{rows(report['changed'][:12], lambda row:
  f"<b>{escape(row['transition_type'])}</b> <code>"
  f"{escape(row.get('entity_name') or row['entity_id'])}.{escape(row['attribute'])}</code> "
  f"{escape(_arrow(row))}<div class='why'>{escape(row['rationale'])}</div>")}</ul>

<h2>Conflicts</h2>
<ul>{rows(report['new_conflicts'][:10], lambda row:
  f"<code>{escape(row['attribute'])}</code> {escape(row['note'])} "
  f"<span class='muted'>severity {row['severity']:.2f}</span>")}</ul>

<h2>Decisions</h2>
<ul>{rows(report['decidable'] + report['blocked'], lambda row:
  f"{escape(row['question'])} <span class='muted'>readiness {row['readiness']:.2f} — "
  f"{escape(row['verdict'])}</span>")}</ul>

<h2>Do next</h2>
<ul>{rows(report['next_actions'], lambda row:
  f"{escape(row['title'])} <span class='muted'>+{row['expected_confidence_gain']:.2f} "
  f"confidence, ~{row['effort_days']:g}d</span>")}</ul>
"""
