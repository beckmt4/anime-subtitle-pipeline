# P0-B3: Generalize benchmark language routing

## Summary
Remove JP/EN-only benchmark assumptions and route benchmark generation via active language pack contract.

## Acceptance criteria
- [ ] `core/benchmark` uses active source/target language values from pack/runtime.
- [ ] JP-specific translation entrypoint names are replaced with language-agnostic paths in benchmark flow.
- [ ] Benchmark metadata records source/target language cleanly.
- [ ] Fixtures/tests run for at least one non-JA translation pack.

## Dependencies
- P0-B1
