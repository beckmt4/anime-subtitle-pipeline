# Spec — Issue #33: Replace smoke-script-only validation with real tests + CI

**Issue:** #33 (rename file to actual number after issue is created)
**Status:** implemented

---

## Problem

The repo's current validation relies on root-level scripts (`test_pipeline.py`,
`test_models_and_inspect.py`, etc.) that require live local services — ffmpeg,
Faster-Whisper, Ollama, GPU. They cannot run in CI. As a result, there is no
automated merge gate: every PR merged on trust alone.

`test_pipeline.py` is useful for manual system validation but should not be the
*only* validation gate.

## Scope

**In scope:**
- Deterministic unit tests for: `media_inspect`, `compare_core`, `config`,
  source-selection helpers in `orchestrator`, constraint enforcement in `llm_polish`
- GitHub Actions CI workflow: lint + tests on every push / PR
- Small deterministic fixtures (ffprobe JSON, config YAML)
- `pytest.ini` and `setup.cfg` for project test/lint config

**Out of scope:**
- Moving or rewriting existing root-level test scripts
- Fixing pre-existing style issues in source files (W293, E501, F401)
- GPU/LLM tests (remain `@pytest.mark.integration`, excluded from default CI run)
- Full end-to-end pipeline test in CI (requires ffmpeg + model downloads)

## Design

### Test boundaries

| Source module | What is tested | How |
|---|---|---|
| `media_inspect` | `_norm_lang`, ffprobe JSON parsing, bitmap detection, `choose_audio_track` | monkeypatched `subprocess.run` |
| `compare_core` | `compute_overlap`, `align_segments`, `compute_metrics` | pure Python + mocked jiwer/sacrebleu |
| `config` | YAML load, profile merge, dir creation, missing file | real `Config` with `tmp_path` YAMLs |
| `orchestrator` | `_lang_matches`, `_first_text_sub`, `_first_audio_order` | direct import, no mocking needed |
| `llm_polish` | `_enforce_constraints`, `enforce_constraints_on_candidate`, `_CJK_RE`, `_recover_leading_english` | mock `Config` |

### Heavy-dep stubbing strategy

`orchestrator`, `llm_polish`, and `asr` import ML/GPU packages at module level
(`faster_whisper`, `torch`, `transformers`, `pysubs2`, `opentelemetry`). These
are not installable in CI without GPU support.

`tests/conftest.py` stubs these packages via `sys.modules.setdefault` before
any test file imports. When the packages are actually installed (dev machine),
`setdefault` is a no-op and the real packages are used.

### CI dependencies

`requirements-ci.txt` contains only: `pyyaml`, `requests`, `pytest`, `flake8`.
No GPU/ML packages. No ffmpeg.

### Lint scope

`flake8 --select=E9,F --extend-ignore=F401,F841` — catches syntax errors and
undefined names; ignores pre-existing unused-import noise without requiring a
style migration PR.

## Acceptance criteria

See `acceptance/33-real-tests-and-ci.md`.

## Open questions at implementation time

- None. All design decisions made during implementation.

## Notes

- Root-level test files (`test_pipeline.py`, etc.) are preserved as-is and
  reclassified as manual system validation.
- File numbers (33) are placeholders — rename once the GitHub issue is created.
