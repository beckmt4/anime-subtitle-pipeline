# Acceptance criteria — Issue #38: llm_polish drift guard and source-context validation

**Issue:** #38
**Status:** met

---

## Criteria

### Source-context preservation
- [x] `polish_candidate()` accepts optional `ja_candidate: Optional[SubtitleCandidate]`
- [x] When `ja_candidate` segment count matches `candidate` segment count, each
      segment is polished with its corresponding Japanese text passed as `text_ja`
- [x] When counts differ, a warning is logged and `text_ja=""` is used (safe fallback)
- [x] When `ja_candidate` is `None`, `text_ja=""` is used (backwards compatible)
- [x] `polish_candidate_with_llm()` accepts and forwards `ja_candidate`
- [x] Orchestrator `embedded_jp_mt` path passes `ja_candidate`
- [x] Orchestrator `ja_audio_asr_mt` path passes `ja_asr_candidate`
- [x] Orchestrator `untagged_audio_asr_mt` path passes `ja_asr_candidate`

### Per-segment drift detection
- [x] `check_drift()` from `subtitle_corrector` applied per segment in
      `polish_candidate()` and `polish_segments()`
- [x] Drift-flagged segments (noun change or length ratio) revert to raw MT text
- [x] Non-drift polished segments are accepted

### Stock-phrase collapse guard
- [x] `_is_stock_phrase_collapse(raw_texts, polished_texts)` implemented
- [x] Returns `True` only when ≥2 segments, all polished outputs are identical,
      that output is a known stock phrase, and raw inputs were diverse
- [x] When collapse is detected, all segments are reverted to raw MT
- [x] Known stock phrases: `sure thing`, `got it`, `here you go`, `oh my god`,
      `okay`, `alright` (with/without punctuation)

### Structured logging / counters
- [x] `PolishStats(total, polished, reverted, unchanged)` named tuple exported
- [x] `polish_stats` dict stored in output `SubtitleCandidate.meta`
- [x] `[llm_polish]` summary log line emitted at end of each run

### Regression tests (all in `tests/test_llm_polish_drift.py`)
- [x] Distinct raw lines must not all collapse to `Sure thing.`
- [x] Distinct raw lines must not all collapse to `Got it.`
- [x] Single-segment batch is not flagged as collapse
- [x] Identical raw inputs with same output are not flagged as collapse
- [x] Unknown (non-stock) repeated output is not flagged as collapse
- [x] Collapse detection is case-insensitive
- [x] `PolishStats` fields and `_asdict()` work correctly
- [x] Noun change (Alan Elburn → Alan) reverts segment, counted as `reverted`
- [x] Accepted fluency fix counted as `polished`
- [x] Length-ratio compression reverts segment
- [x] Unchanged output counted as `unchanged`
- [x] Mixed batch (accepted / reverted / unchanged) tallies correctly
- [x] `ja_candidate` Japanese text forwarded to `polish_text`
- [x] Mismatched `ja_candidate` count falls back to empty Japanese context
- [x] No `ja_candidate` defaults to empty Japanese context
- [x] `polish_candidate_with_llm` forwards `ja_candidate` to `LLMPolisher`
- [x] Named-term regression: `Alan Elburn` name drop triggers drift revert
- [x] Named-term regression: `Mizmelis` → `Mizmélis` mutation triggers drift revert
- [x] Named-term regression: `Dallas` → `dollars` substitution triggers drift revert

---

## Test evidence

Tests run: `pytest tests/test_llm_polish_drift.py -v`

**Result:** 24 passed

Full suite: `pytest tests/ -q`

**Result:** 236 passed

---

## Notes

- The `_STOCK_PHRASES` frozenset can be extended without touching test logic.
- `check_drift` is intentionally reused from `subtitle_corrector` to avoid
  duplicating the noun-extraction and length-ratio logic.
- The `ja_candidate` parameter is optional and backwards compatible; existing
  callers that do not pass it receive the same behaviour as before (empty JP context).
