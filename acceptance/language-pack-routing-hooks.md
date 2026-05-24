# Acceptance criteria — Refactor Japanese-only generate orchestration into language-pack routing hooks

## Criteria mapping

- [x] Core orchestration no longer directly hardcodes the current JP→EN routing assumptions in the main decision tree.
- [x] Source-language and target-language concepts are explicit in the generate path.
- [x] Language-specific routing behavior is delegated through a language-pack routing hook.
- [x] Heuristic fallback behavior is routed through explicit language-pack policy.
- [x] Tests cover the refactored orchestration boundaries under `tests/`.
- [x] Required architecture doc updates land in the same PR.
- [x] Acceptance criteria are mapped in `acceptance/`.

## Test evidence

```bash
python -m pytest tests/test_orchestrator.py tests/test_packs_language_ja_en.py \
  tests/test_main_registry_integration.py -v --tb=short
```
