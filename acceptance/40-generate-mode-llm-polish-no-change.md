# Acceptance criteria — Issue #40: generate mode LLM polish no-change detection

**Issue:** #40
**Status:** met

---

## Criteria

### Core logic (`_compare_candidates`)
- [x] Returns `polish_status = "fallback"` when `polished.meta["fallback"]` is `True`
- [x] Returns `polish_status = "no_change"` when every segment text is identical
- [x] Returns `polish_status = "changed"` when at least one segment differs
- [x] `segments_changed` counts segments whose text changed (strip-compared)
- [x] `segments_unchanged` counts segments whose text did not change
- [x] Length mismatch between raw and polished candidates counts toward `segments_changed`
- [x] `_compare_candidates` exported in `__all__` alongside `run_generate`

### Logging (`_log_polish_stats`)
- [x] `"fallback"` → `logger.info` message notes pass-through count
- [x] `"no_change"` → `logger.warning` with total unchanged segment count
- [x] `"changed"` → `logger.info` with changed and unchanged counts

### Generate-mode metadata
- [x] `polish_status` present in `run_generate` return dict when LLM polish ran
- [x] `segments_changed` present when LLM polish ran
- [x] `segments_unchanged` present when LLM polish ran
- [x] All three fields absent when strategy bypasses LLM polish (`embedded_en`, `en_audio_asr`)
- [x] Applied to all three MT+LLM strategies: `embedded_jp_mt`, `ja_audio_asr_mt`,
      `untagged_audio_asr_mt`

### Tests
- [x] `test_compare_candidates_changed` — one segment changed, one unchanged
- [x] `test_compare_candidates_no_change` — all segments identical → `no_change`
- [x] `test_compare_candidates_fallback` — `meta["fallback"]=True` → `fallback`
- [x] `test_polish_status_changed_in_metadata` — changed polish → correct metadata
- [x] `test_polish_status_no_change_in_metadata` — no-op polish → `no_change` in metadata
- [x] `test_polish_status_fallback_in_metadata` — fallback polish → `fallback` in metadata
- [x] `test_no_polish_status_for_non_mt_strategies` — `embedded_en` omits `polish_status`

---

## Test evidence

Tests run: `python -m pytest tests/ test_orchestrator.py -v`

**Result:** 224 passed

---

## Notes

- The final `.en.srt` is still written to disk even when `polish_status` is
  `no_change`.  The goal of this change is to make the outcome explicit in
  metadata and logs, not to suppress output.
- The `polish_status` field uses the same `no_change` vocabulary already
  established by `subtitle_pipeline.py` for the standalone corrector path.
- Comparison uses `.strip()` on both sides to avoid false positives from
  trailing whitespace differences introduced by constraint enforcement.
