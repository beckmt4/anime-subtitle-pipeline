# tests/

Automated tests for the subtitle intelligence platform.

## Current state

Test files currently live in the project root as `test_*.py`. This is a known layout debt. New tests should be written here in `tests/`. Existing root-level tests will be migrated here progressively — tracked as part of the Phase 1/2 module migration.

**Existing test files (in root):**
- `test_asr_candidate.py` — ASR candidate generation
- `test_audio_selection.py` — audio track selection logic
- `test_benchmark.py` — benchmark orchestration
- `test_benchmark_generalized.py` — generalized benchmark cases
- `test_candidate_pipeline.py` — candidate processing pipeline
- `test_models_and_inspect.py` — data structures and media inspection
- `test_orchestrator.py` — generation strategy decision tree
- `test_pipeline.py` — legacy pipeline end-to-end
- `test_subtitle_utils.py` — embedded subtitle extraction

## Running tests

```bash
pytest                        # run all tests
pytest test_orchestrator.py   # run a specific test file
pytest -m "not integration"   # skip GPU/LLM-dependent tests
```

## Test requirements

- Use `pytest`.
- New test files go here in `tests/`, named `test_<module>.py`.
- Tests that require a GPU, a running Ollama instance, or network access must be marked:
  ```python
  @pytest.mark.integration
  def test_asr_full_pipeline():
      ...
  ```
- Tests must not depend on files in `inbox/`, `outbox/`, or `temp/`. Use `fixtures/` for test inputs.
- Tests must be deterministic. Do not write tests that pass intermittently.

## Structure (target)

As modules migrate to `core/` and `packs/`, tests follow:

```
tests/
  core/
    test_media.py
    test_extract.py
    test_asr.py
    test_mt.py
    test_polish.py
    test_subtitles.py
    test_benchmark.py
    test_runtime.py
  packs/
    test_language_ja_en.py
    test_domain_anime.py
  fixtures/  → see fixtures/ at repo root
```

This structure is the target, not the current state. Migrate incrementally.
