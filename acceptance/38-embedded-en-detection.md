# Acceptance criteria — Issue #38: Fix embedded English subtitle detection in generate mode

**Issue:** #38
**Status:** met

---

## Criteria

### Language detection
- [x] `_lang_matches` correctly handles BCP-47 regional subtags (`en-AU`, `en-CA`, `en-US`, etc.)
- [x] `_lang_matches` correctly handles ISO 639-2 codes (`eng`, `jpn`)
- [x] `_lang_matches` correctly handles full language names (`English`, `Japanese`) via `LANG_MAP`
- [x] `_first_text_sub` skips bitmap subtitle tracks and logs the reason
- [x] `_first_text_sub` logs accepted and rejected subtitle streams with codec and language info
- [x] `_first_audio_order` logs accepted and rejected audio streams with codec and language info

### Strategy selection
- [x] `run_generate()` selects `embedded_en` for a file with a valid English text subtitle
- [x] `run_generate()` selects `embedded_en` when the EN subtitle is tagged `eng` (ISO 639-2)
- [x] `run_generate()` selects `embedded_en` when the EN subtitle is tagged `en-US` (BCP-47)
- [x] `run_generate()` does NOT select `embedded_en` when `skip_embedded_en=True`
- [x] `skip_embedded_en=True` preserves existing behavior (forces generation path)

### Regression fixtures
- [x] `fixtures/ffprobe/couple_of_cuckoos_s01e01.json` — JA audio, bitmap JA sub, text EN sub (`eng` tag)
- [x] `fixtures/ffprobe/once_upon_a_crime.json` — JA audio, JA subs, text EN sub (`en-US` BCP-47 tag)

### Tests
- [x] `tests/test_source_selection.py` — BCP-47 regional variant tests added to `TestLangMatches`
- [x] `tests/test_source_selection.py` — Regression tests for `eng`-tagged and `en-US`-tagged streams
- [x] `tests/test_media_inspect.py` — Full language name normalization tests added
- [x] `tests/test_media_inspect.py` — Regression fixture parsing tests for both failing scenarios
- [x] `test_orchestrator.py` — `test_embedded_en_selected_with_eng_tag` passes
- [x] `test_orchestrator.py` — `test_embedded_en_selected_with_bcp47_en_us_tag` passes
- [x] `test_orchestrator.py` — `test_skip_embedded_en_forces_generation` passes

### Documentation
- [x] Spec written in `specs/38-embedded-en-detection.md`

---

## Test evidence

Tests run: `python -m pytest tests/ test_orchestrator.py -v`

All tests pass, including new regression tests for:
- A Couple of Cuckoos (`eng`-tagged EN subtitle)
- Once Upon a Crime (`en-US` BCP-47 EN subtitle)

---

## Notes

- The root cause was that `_lang_matches` did not handle BCP-47 regional subtags
  (e.g. `en-AU`, `en-US`, `en-CA`). A prefix split on `-` now catches all of these.
- `LANG_MAP` was extended with full language names (`"english"` → `"en"`,
  `"japanese"` → `"ja"`) to cover muxers that write verbose names instead of codes.
- No changes to the decision tree logic were required — the preference order was
  already correct; only the language detection was broken.
- `skip_embedded_en` behavior is preserved and covered by a dedicated test.
