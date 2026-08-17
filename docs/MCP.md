# The engine inside your assistant (MCP)

`lce mcp` runs the engine as an [MCP](https://modelcontextprotocol.io) server over
stdio. Any MCP client — Claude Desktop, Claude Code, Cursor, or your own — can
then read the graph, cite its confidence, and propose observations.

This is the shortest path to adoption: **no new interface, no syntax to learn.**
The assistant your team already talks to gains a memory that knows what it does
not know.

## Setup

```bash
lce mcp --print-config
```

```json
{
  "mcpServers": {
    "living-context": {
      "command": "lce",
      "args": ["--root", "/abs/path/to/your-repo", "--project", "acme", "mcp"]
    }
  }
}
```

- **Claude Desktop** — paste into `claude_desktop_config.json` and restart.
- **Claude Code** — `claude mcp add living-context -- lce --root "$PWD" mcp`
- **Cursor / others** — any client that speaks stdio MCP takes the same block.

No network, no key. The server reads the same SQLite file the CLI does.

## Tools

| Tool | What it is for |
| --- | --- |
| `lce_context` | **The one that matters.** Decision-scoped pack: relevant beliefs with confidence and provenance, what changed, conflicts, unknowns, next actions. |
| `lce_why` | Explain one belief: evidence, independent sources, method ceiling, history, what would move it. |
| `lce_state` | Current beliefs, optionally for one entity. |
| `lce_delta` | State changes with the reason each belief moved. |
| `lce_contradictions` | Open conflicts with both sides and severity. |
| `lce_unknowns` | Open questions by impact, with the decision each blocks. |
| `lce_actions` | Ranked verification actions. |
| `lce_decisions` | The decision board with readiness and the weakest link. |
| `lce_digest` | The recurring what-changed summary. |
| `lce_propose_observation` | Record something just learned — **staged, never applied**. |
| `lce_packet_schema` | The packet schema and extraction rules. |
| `lce_review_queue` | What is waiting for a human, and acceptance rates per source. |

The server also sends `instructions` on initialize, telling the client to call
`lce_context` before answering questions about the project and to cite the
confidence it finds.

## Prompts

The whole prompt library is exposed as MCP prompts, so `extract`,
`interview-guide`, `adjudicate`, `actions`, `decision-brief`, and `review-delta`
appear in the client's prompt picker, already filled in with live state.

## The loop, from inside a conversation

```
You:  We just got off a call with Omar at Brightforge.
      He said they already pay a consultant ~15k a year for audit prep.

Claude: [lce_context "willingness to pay"]  → sees the belief is held at 0.24
                                              on one assertion
        [lce_propose_observation]           → stages a transaction-adjacent
                                              interview claim with the quote
        "Staged for review. This contradicts the founder's $2k/mo assumption
         (held at 0.07), so the engine will flag the conflict once accepted."

You:  lce review --accept <id>
```

Nothing entered the graph until you accepted it. That is the point: the assistant
gets to be useful and wrong, and the graph stays clean.

## What the server will not do

- **It cannot apply state.** `lce_propose_observation` stages; there is no accept
  tool. Accepting is a deliberate human act through the CLI or the review queue.
- **It cannot resolve contradictions, close decisions, or merge entities.** Those
  are judgements with consequences, and an assistant reading a transcript is not
  positioned to make them.
- **It reports errors as tool errors**, not crashes, so a bad call never takes the
  session down.

That boundary is what makes it safe to leave connected.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `project_required` | Pass `--project` in the args, or set `project` in `.lce/config.json`. |
| Tools appear but return nothing | The graph is empty for that project — run `lce ingest`. |
| Client shows no tools | The client is not launching `lce`; use an absolute path to the binary in `command`. |
| Proposals never appear | You are looking at the wrong project or root; `lce review --project <id>`. |
