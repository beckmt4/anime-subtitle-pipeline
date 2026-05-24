# P0-C2: OCR confidence, routing, and review visibility

## Summary
Ensure OCR confidence is persisted and drives policy routing and review UX.

## Acceptance criteria
- [ ] Per-segment OCR confidence is persisted in candidate metadata and QC output.
- [ ] OCR warning density can trigger review routing via configurable thresholds.
- [ ] Review UI visibly surfaces OCR confidence warnings per segment.
- [ ] Tests cover OCR-low-confidence routing behavior.

## Dependencies
- P0-C1
