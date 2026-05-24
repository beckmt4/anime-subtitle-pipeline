# P1-D1: Review state machine and dedupe hardening

## Summary
Formalize review task lifecycle and prevent duplicate pending tasks.

## Acceptance criteria
- [ ] Review task states are explicit (`pending`, `approved`, `rejected`, `superseded`).
- [ ] Re-running generate does not create duplicate pending tasks for the same candidate/media context.
- [ ] Queue output surfaces task state clearly.
- [ ] Tests cover approve/reject/supersede/dedupe behavior.

## Dependencies
- P0-B (B1/B2/B3), P0-C (C1/C2)
