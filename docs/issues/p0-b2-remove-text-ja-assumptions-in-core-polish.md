# P0-B2: Remove `text_ja` assumptions in `core/polish`

## Summary
Refactor polish APIs and prompts to use language-agnostic source text interfaces.

## Acceptance criteria
- [ ] Public polish API uses language-agnostic names (`source_text`, `source_lang`).
- [ ] Prompt construction is delegated to language pack hooks or generic templates.
- [ ] `core/polish` no longer exposes JA-specific argument names in public signatures.
- [ ] Regression tests cover JA and non-JA call paths.

## Dependencies
- P0-B1
