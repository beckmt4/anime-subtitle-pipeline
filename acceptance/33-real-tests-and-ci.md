# Acceptance criteria — Issue #33: Replace smoke-script-only validation with real tests + CI

**Issue:** #33 (rename file to actual number after issue is created)
**Status:** met

---

## Criteria

### Issue and spec
- [x] GitHub issue created or issue markdown file added (`docs/issues/`)
- [x] Spec written in `specs/33-real-tests-and-ci.md`

### Tests
- [x] Real deterministic unit tests added for `media_inspect`
  - [x] Language normalization (`_norm_lang`) — all known codes, case-insensitive, None/empty
  - [x] ffprobe JSON parsing into `AudioStream` / `SubtitleStream` via monkeypatched subprocess
  - [x] Bitmap subtitle detection for all three bitmap codecs
  - [x] `choose_audio_track` — preferred match, fallback, empty streams
  - [x] Failure cases: missing file, ffprobe process failure, invalid JSON
  - [x] subprocess called as a list (injection safety check)
- [x] Real deterministic unit tests added for `compare_core`
  - [x] `compute_overlap` — full, partial, zero, adjacent, contained, symmetric
  - [x] `align_segments` — basic, max-overlap selection, empty ref, empty cand, no-overlap fallback
  - [x] `compute_metrics` — empty inputs, length mismatch, mocked jiwer/sacrebleu
- [x] Real deterministic unit tests added for config loading
  - [x] YAML load — success, missing file, nested key access, default fallback
  - [x] Directory creation — all four dirs created, idempotent on second load
  - [x] Profile override — dev vs prod settings applied correctly
  - [x] Property accessors — llm_enabled, asr_language, subtitle durations, prompt placeholders
- [x] Real deterministic unit tests added for source selection
  - [x] `_lang_matches` — ja/en variants, None/empty, case-insensitive, unknown target
  - [x] `_first_text_sub` — found, skips bitmap, language mismatch, no streams, returns first
  - [x] `_first_audio_order` — found, not found, no streams, jpn/eng raw tags
- [x] Real deterministic unit tests added for constraint enforcement
  - [x] `_enforce_constraints` — empty, normal, spaces, newlines, tabs, CR+LF
  - [x] `enforce_constraints_on_candidate` — text normalized, timing preserved, meta flag set
  - [x] `_CJK_RE` — detects hiragana, katakana, CJK, Korean, fullwidth punct; ignores Latin
  - [x] `_recover_leading_english` — recovers appended CJK, returns None for interspersed/short

### Fixtures
- [x] `fixtures/ffprobe/minimal_ja_audio.json` — single JA audio track
- [x] `fixtures/ffprobe/multi_stream.json` — JA+EN audio, EN text sub, JA bitmap sub
- [x] `fixtures/config/minimal.yaml` — minimal config for loading tests

### CI
- [x] `.github/workflows/ci.yml` added
- [x] CI runs on push and pull_request
- [x] CI installs only `requirements-ci.txt` (no GPU/ML packages)
- [x] CI runs flake8 (E9 + F, minus pre-existing F401/F841)
- [x] CI runs `pytest tests/ -m "not integration"`
- [x] CI does NOT require ffmpeg, Whisper, Ollama, or model downloads

### Repo assets
- [x] `pytest.ini` added (testpaths, pythonpath, marker definition)
- [x] `setup.cfg` added (flake8 config)
- [x] `requirements-ci.txt` added

### Manual validation preserved
- [x] `test_pipeline.py` is unchanged
- [x] Root-level test scripts are unchanged

### Docs
- [x] `CONTRIBUTING.md` updated with local lint/test commands
- [x] README.md updated with CI badge section (or left for follow-up if README is minimal)

---

## Test evidence

Tests run locally: `venv/Scripts/python -m pytest tests/ -v --tb=short -m "not integration"`

**Result:** 126 passed in 0.99s

Lint run locally: `venv/Scripts/python -m flake8 ... --select=E9,F --extend-ignore=F401,F841`

**Result:** exit 0 (no output)

---

## Notes

- File number 33 is a placeholder — rename to actual GitHub issue number.
- F401/F841 are excluded from CI lint because pre-existing violations in source
  files would block CI without a separate style cleanup PR. These should be fixed
  in a follow-up chore PR.
- `sys.modules.setdefault` stubs in `tests/conftest.py` are no-ops on the dev
  machine where packages are already installed.
