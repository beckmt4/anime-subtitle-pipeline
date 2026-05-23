# Acceptance Mapping - Review correction dataset exports

## Implemented

- Added dataset export helpers in `core/translation/dataset_export.py` to export:
  - approved correction JSONL
  - benchmark reference fixture JSONL
  - SFT/message-format JSONL
  - preference-pair JSONL
- Added `TranslationMemoryStore.list_records(...)` in
  `core/translation/memory.py` so filtered translation-memory records can be
  exported cleanly.
- Added CLI export script:
  - `scripts/export_review_corrections.py`
  - supports language/domain filtering and optional output toggles.
- Added docs for dataset schema, validation, and LoRA/SFT safety checks:
  - `docs/review_dataset_exports.md`
  - `README.md` section linking to the export workflow.

## Tests

- `tests/test_translation_dataset_export.py`
  - SFT export shape and metadata assertions
  - preference-pair export shape assertions
  - invalid/incomplete row skip reporting behavior
