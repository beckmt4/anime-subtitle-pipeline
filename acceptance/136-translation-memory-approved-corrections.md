# Acceptance Mapping - Issue #136: Translation Memory and Approved Corrections

## Implemented

- Added local translation-memory module:
  - `core/translation/memory.py`
  - `ApprovedCorrectionRecord` data model
  - `TranslationMemoryStore` JSONL-backed add/query/export API
  - deterministic source-text relevance query with optional `domain` and
    `language_pack` filters
- Exposed translation-memory helpers from `core.translation`.
- `mt.LLMDirectTranslator` now supports optional prompt injection of retrieved
  approved corrections via `translation.memory.*` config.
  - Applies to both `llm_direct` and `hybrid` (hybrid uses the same prompt path).
- Review workflow now supports persisting approved edited lines into translation
  memory during `approve_review_task(..., translation_memory=...)`.
- Updated docs in `README.md` with correction lifecycle/local-only storage note
  and `translation.memory` config settings.

## Tests

- `tests/test_translation_memory.py`
  - add/query/export JSONL behavior
  - prompt block formatting
- `tests/test_translation_engine_selector.py`
  - LLM prompt includes approved translation-memory entries when enabled
- `tests/test_review_workflow.py`
  - approving edited segment stores approved correction in memory
