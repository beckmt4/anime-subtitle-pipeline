# P1-F2: Unskip language-hardcoding architecture guards

## Summary
Activate currently skipped architecture guard tests once JA-specific assumptions are removed.

## Acceptance criteria
- [ ] Skipped guard tests for hardcoded JA/EN prompt and `source_text_ja` are unskipped.
- [ ] CI fails if hardcoded JA-only assumptions are reintroduced in guarded modules.
- [ ] Guard coverage includes `core/mt` and `core/polish` public API language assumptions.

## Dependencies
- P0-B1
- P0-B2
