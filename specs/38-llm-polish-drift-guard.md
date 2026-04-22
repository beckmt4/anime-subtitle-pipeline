# Spec — Issue #38: llm_polish drift guard and source-context validation

**Issue:** #38
**Status:** implemented

---

## Problem

The `llm_polish` path can rewrite unrelated subtitle lines into repeated stock
phrases such as `Sure thing.`, `Got it.`, `Here you go.`, and `Oh my god!`.
This is semantic corruption, not style drift.

Two root causes:

1. `polish_candidate()` called `polish_text()` with `text_ja=""`, so candidate
   polishing happened without the original Japanese context.
2. Unlike `subtitle_corrector.py`, `llm_polish.py` had no drift-detection /
   revert guard for bad per-segment rewrites.

---

## Scope

**In scope:**
- Accept optional `ja_candidate` param in `polish_candidate()` and
  `polish_candidate_with_llm()` to carry Japanese source context per segment.
- Import and apply `check_drift()` from `subtitle_corrector` per segment.
- Revert drift-flagged segments to raw MT text.
- Add `_is_stock_phrase_collapse()` guard: detect when diverse raw inputs all
  collapse to a single known filler phrase and revert the whole batch.
- Add `PolishStats` named tuple: `(total, polished, reverted, unchanged)`.
- Emit structured `[llm_polish]` log lines with the counters.
- Apply the same drift detection in `polish_segments()` (legacy Segment path).
- Store `polish_stats` dict in the output `SubtitleCandidate.meta`.
- Update `orchestrator.py` to pass `ja_candidate` / `ja_asr_candidate` through
  to `polish_candidate_with_llm`.
- Regression tests for all failure cases from the issue.
- This spec and an acceptance document.

**Out of scope:**
- NLP-based POS tagging (regex extraction from `subtitle_corrector` only).
- Changing the LLM system prompt.
- Reprocessing drift-flagged segments with a stricter prompt.
- Glossary / term-list based validation.

---

## Design

### `PolishStats(total, polished, reverted, unchanged)`

```python
class PolishStats(NamedTuple):
    total: int
    polished: int    # accepted polished output (changed, not reverted)
    reverted: int    # drift-flagged, reverted to raw MT
    unchanged: int   # LLM returned identical text
```

Stored in `SubtitleCandidate.meta["polish_stats"]` as a dict.

### `_is_stock_phrase_collapse(raw_texts, polished_texts) -> bool`

Returns `True` when:
- `len(polished_texts) >= 2`  (single segment cannot be a collapse)
- All polished outputs are identical (same string after strip + lower)
- That output is in the `_STOCK_PHRASES` frozenset
- The raw inputs are **not** all identical (diverse input → same output)

The `_STOCK_PHRASES` set covers: `sure thing`, `got it`, `here you go`,
`oh my god`, `okay`, `alright` (with and without trailing `.` or `!`).

When collapse is detected the **entire batch** is reverted and all segments
are counted as `reverted`.

### `LLMPolisher.polish_candidate(candidate, ja_candidate=None, style=None)`

New optional parameter `ja_candidate: Optional[SubtitleCandidate]`.

- If `ja_candidate` is provided **and** its segment count matches
  `candidate.segment_count`, each segment is polished with its corresponding
  Japanese source text passed as `text_ja`.
- If counts differ, a warning is logged and `text_ja=""` is used for all
  segments (safe fallback, same behaviour as before).
- If `ja_candidate` is `None`, `text_ja=""` for all segments (backwards
  compatible).

Processing order (per batch):
```
1. Collect polished text for every segment.
2. Run stock-phrase collapse check on the full batch.
   → If True: revert all, return.
3. For each segment, run check_drift(raw, polished).
   → If drift: revert to raw, count as reverted.
   → Elif identical: count as unchanged.
   → Else: accept polished, count as polished.
4. Log [llm_polish] summary line.
5. Return SubtitleCandidate with polish_stats in meta.
```

### `polish_candidate_with_llm(candidate, config, ja_candidate=None, style=None)`

Updated signature. `ja_candidate` is forwarded to
`LLMPolisher.polish_candidate`.

### `LLMPolisher.polish_segments()` (legacy `Segment` path)

Same stock-phrase collapse guard + per-segment `check_drift` revert applied.
Stats logged at end (no `PolishStats` object returned — existing return type
is `List[Segment]`).

### Orchestrator integration

`orchestrator.py` updated to pass the available Japanese candidate in all three
MT paths:
- `embedded_jp_mt`: passes `ja_candidate`
- `ja_audio_asr_mt`: passes `ja_asr_candidate`
- `untagged_audio_asr_mt`: passes `ja_asr_candidate`

### Summary log line format

```
[llm_polish] polish_candidate <id>: total=N polished=N reverted=N unchanged=N
```

---

## Acceptance criteria

See `acceptance/38-llm-polish-drift-guard.md`.
