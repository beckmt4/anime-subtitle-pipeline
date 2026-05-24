# P1-F1: Add explicit smoke test module

## Summary
Introduce one explicit smoke suite for core product paths runnable in CI.

## Acceptance criteria
- [ ] `tests/test_smoke.py` exists and covers inspect-only, text-sub path, ASR path, MT path, and review approval path.
- [ ] Smoke tests run in CI without GPU/model downloads.
- [ ] Smoke suite is referenced from acceptance index/docs.

## Dependencies
- P0-B (language-agnostic hardening)
