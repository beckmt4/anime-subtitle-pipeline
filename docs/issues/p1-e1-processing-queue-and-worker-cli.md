# P1-E1: SQLite processing queue and worker CLI mode

## Summary
Add durable queue + worker execution mode for repeatable library automation.

## Acceptance criteria
- [ ] SQLite queue model exists with explicit states and transitions.
- [ ] `main.py --mode worker` supports `run`, `watch`, `retry-failed`, `resume`, `status`.
- [ ] Queue item links to registry run id and error context.
- [ ] Worker execution is safe and idempotent for interrupted runs.
- [ ] Tests cover core state transitions.

## Dependencies
- P0-A1
