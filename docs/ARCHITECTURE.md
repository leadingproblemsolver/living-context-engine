# Architecture

```text
files/directories
→ deterministic line extractor
→ source-linked context records
→ replace-by-source SQLite persistence
→ query/timeline/context-pack/export/API
```

Source replacement is atomic per file: re-ingesting a changed file removes its old records and inserts records tied to the new source hash. External callers cannot mutate data through the HTTP service.
