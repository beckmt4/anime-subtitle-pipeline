# P0-B1: Remove hardcoded JA→EN assumptions from `core/mt`

## Summary
Make `core/mt` language-agnostic by removing hardcoded JA/EN prompt and metadata assumptions.

## Acceptance criteria
- [ ] No hardcoded `"You are translating Japanese dialogue into English subtitles"` string in `core/mt`.
- [ ] `source_text_ja` usage is replaced with a language-agnostic source-text contract.
- [ ] Translation memory lookup source/target language values are supplied from active pack/runtime, not hardcoded.
- [ ] Existing translation tests pass.
- [ ] At least one test verifies non-JA prompt hook support.

## Dependencies
- P0-A1
