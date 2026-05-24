# P1-E2: Recursive scanner and dedupe policy

## Summary
Add recursive library discovery, skip/force behavior, and stable dedupe constraints for queue ingestion.

## Acceptance criteria
- [ ] Recursive scanner discovers configured media extensions.
- [ ] Existing `.en.srt` sidecar causes skip unless `--force` is set.
- [ ] Stable dedupe is enforced using path/hash/state.
- [ ] Discovery summary reports found/skipped/queued counts.
- [ ] Tests cover duplicate prevention and force override.

## Dependencies
- P1-E1
