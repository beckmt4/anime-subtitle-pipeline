# Acceptance criteria — Issue #35: subtitle_corrector drift detection

**Issue:** #35
**Status:** met

---

## Criteria

### Core logic
- [x] `_extract_nouns(text)` extracts capitalized words (2+ chars) and quoted terms
- [x] `check_drift(raw, llm)` returns `(False, "", "")` when texts are identical
- [x] `check_drift` returns `(True, "noun_change", noun)` when a noun is missing
- [x] `check_drift` returns `(True, "length_ratio", ratio_str)` when word count ratio > 1.4 or < 0.6
- [x] Noun check takes priority over length check
- [x] Drift-flagged cues use raw text in the output SRT
- [x] Non-drift LLM corrections are accepted as before

### Reporting
- [x] Summary line printed at end of every non-dry-run call
- [x] Summary format: `[corrector] {label}: N cues processed, N corrected, N drift-reverted`
- [x] `--verbose` prints `DRIFT REVERTED #N:` block with raw, llm, reason per flagged cue
- [x] `--drift-log PATH` writes one JSON line per drift event

### Tests
- [x] `test_extract_nouns` — capitalized words, quoted terms, mixed, empty input
- [x] `test_check_drift_identical` — no drift on identical text
- [x] `test_check_drift_noun_change` — noun missing from corrected → drift flagged
- [x] `test_check_drift_noun_preserved` — noun present → no drift
- [x] `test_check_drift_length_too_long` — >1.4x word count → drift
- [x] `test_check_drift_length_too_short` — <0.6x word count → drift
- [x] `test_check_drift_length_acceptable` — within range → no drift
- [x] `test_check_drift_noun_before_length` — noun check takes priority
- [x] `test_check_drift_quoted_terms` — quoted term preserved/missing

### API / CLI
- [x] `correct_srt()` accepts `verbose`, `drift_log`, `label` kwargs
- [x] Existing callers with no new kwargs are unaffected
- [x] `--verbose` CLI arg wired up
- [x] `--drift-log` CLI arg wired up
- [x] `check_drift` and `_extract_nouns` exported in `__all__`

---

## Test evidence

Tests run: `pytest tests/test_subtitle_corrector.py -v`

**Result:** all tests passed

Lint: `flake8 subtitle_corrector.py --select=E9,F --extend-ignore=F401,F841`

**Result:** exit 0

---

## Notes

- `_extract_nouns` intentionally includes sentence-initial words (over-detection is
  safer than under-detection for the noun-preservation goal).
- Length ratio check is skipped when raw text has zero words (divide-by-zero guard).
