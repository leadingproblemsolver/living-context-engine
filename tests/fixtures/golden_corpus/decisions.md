# Decisions

Decision: We will use SQLite as the structured state layer for the Living Context Engine.
This decision was made because the system must run locally without any external database dependency.

Decision: We chose deterministic heuristic signal extraction over an LLM-based extractor for the base runtime.
This keeps the base install free of API keys and network calls.

Decision: Retrieval hits will use one canonical schema across query, brief, and compile.
