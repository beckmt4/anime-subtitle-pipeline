# Acceptance Mapping - Issue #134: Glossary and Name Enforcement for Packs

## Implemented

- Added pack-owned starter terminology files:
  - `packs/language/ja_en/glossary.yml`
  - `packs/language/ja_en/names.yml`
  - `packs/language/ja_en/style.yml`
  - `packs/domain/anime/glossary.yml`
  - `packs/domain/anime/style.yml`
  - `packs/domain/jav/glossary.yml`
  - `packs/domain/jav/style.yml`
- Added `core/translation/glossary.py` loader/normalization API:
  - Resolves active language/domain packs from config
  - Loads glossary/name/style YAML data
  - Applies precedence (`domain` overrides `language` for duplicate terms)
  - Builds per-cue prompt glossary blocks
  - Validates required term/name/honorific drift
- `mt.LLMDirectTranslator` now injects relevant glossary terms into prompt text.
- `translation_qc.run_translation_qc` now emits structured drift findings for
  required terms (mapped to `bad_name`, `bad_honorific`, `wrong_meaning`).

## Tests

- `tests/test_translation_glossary.py`
  - Loader precedence
  - Relevant prompt block injection
  - Required name/honorific drift detection
- `tests/test_translation_engine_selector.py`
  - LLM direct prompt contains glossary enforcement lines for matching terms
- `tests/test_translation_qc.py`
  - Required name/honorific drift surfaced in translation QC findings
- `tests/test_packs_language_ja_en.py`
  - Confirms `glossary.yml`, `names.yml`, and `style.yml` are present
- `tests/test_packs_domain.py`
  - Confirms domain `glossary.yml`/`style.yml` files are present for anime/jav
