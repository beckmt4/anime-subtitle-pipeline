# tests/

Automated tests for the subtitle intelligence platform.

## Current state

Primary automated tests live under `tests/`. Pytest is configured with
`testpaths = .` in `pytest.ini`, so collection still starts at repository root,
but active unit/integration tests are maintained in this directory.

## Running tests

```bash
pytest                        # run all tests
pytest tests/test_orchestrator.py   # run a specific test file
pytest -m "not integration"   # skip GPU/LLM-dependent tests
```

## Test requirements

- Use `pytest`.
- New test files go in `tests/`, named `test_<module>.py`.
- Tests that require a GPU, a running Ollama instance, or network access must be marked:
  ```python
  @pytest.mark.integration
  def test_asr_full_pipeline():
      ...
  ```
- Tests must not depend on files in `inbox/`, `outbox/`, or `temp/`. Use `fixtures/` for test inputs.
- Tests must be deterministic. Do not write tests that pass intermittently.

## Structure

```
tests/
  test_media_inspect.py
  test_orchestrator.py
  test_review_workflow.py
  test_artifacts.py
  ...
```
