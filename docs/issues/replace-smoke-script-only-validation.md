# Issue: Replace smoke-script-only validation with real tests + CI

> Create this issue with:
> ```
> gh issue create \
>   --title "replace smoke-script-only validation with real tests + CI" \
>   --body-file docs/issues/replace-smoke-script-only-validation.md \
>   --label "test,ci,infra"
> ```
> Then rename `specs/33-real-tests-and-ci.md` and `acceptance/33-real-tests-and-ci.md`
> to use the actual issue number.

---

## Problem

The repo's primary validation path is a set of root-level test scripts
(`test_pipeline.py`, `test_models_and_inspect.py`, `test_orchestrator.py`, etc.)
that require live local services — ffmpeg, Faster-Whisper, Ollama, and a GPU.

These scripts cannot run in CI. As a result, there is no automated merge gate.
Every PR merged on trust alone, with no systematic check that basic logic is
correct.

`test_pipeline.py` is useful for manual end-to-end validation but it is not
sufficient as the *only* form of validation.

## Scope

Replace the smoke scripts as the primary merge gate by adding:
- Real deterministic unit tests under `tests/`
- A GitHub Actions CI workflow that runs lint + tests
- Small deterministic fixtures (no binary media, no model downloads)

Keep `test_pipeline.py` as manual system validation. Do not delete or break it.

## Acceptance criteria

- [ ] GitHub Actions CI workflow runs on every push and PR
- [ ] CI runs lint (flake8) and tests (`pytest tests/`) without GPU or live services
- [ ] Deterministic unit tests for: `media_inspect`, `compare_core`, `config`,
      source selection helpers, constraint enforcement
- [ ] Small fixture files added in `fixtures/`
- [ ] `pytest.ini` and `setup.cfg` added for project test/lint configuration
- [ ] `requirements-ci.txt` added (no GPU/ML packages)
- [ ] `test_pipeline.py` unchanged — remains manual system validation
- [ ] Spec in `specs/`
- [ ] Acceptance doc in `acceptance/`

## Implementation checklist

- [ ] Create `tests/conftest.py` with heavy-dep stubs
- [ ] Create `tests/test_media_inspect.py`
- [ ] Create `tests/test_compare_core.py`
- [ ] Create `tests/test_config.py`
- [ ] Create `tests/test_source_selection.py`
- [ ] Create `tests/test_constraints.py`
- [ ] Create `fixtures/ffprobe/minimal_ja_audio.json`
- [ ] Create `fixtures/ffprobe/multi_stream.json`
- [ ] Create `fixtures/config/minimal.yaml`
- [ ] Create `.github/workflows/ci.yml`
- [ ] Create `pytest.ini`
- [ ] Create `setup.cfg` (flake8 config)
- [ ] Create `requirements-ci.txt`
- [ ] Create `specs/<N>-real-tests-and-ci.md`
- [ ] Create `acceptance/<N>-real-tests-and-ci.md`

## Definition of done

- All unit tests pass locally with `pytest tests/`
- Lint passes with `flake8 ... --select=E9,F`
- CI workflow is valid YAML and would pass on Ubuntu (no GPU required)
- `test_pipeline.py` is unchanged
