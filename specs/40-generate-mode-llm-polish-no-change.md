# Spec — Issue #40: generate mode LLM polish no-change detection

**Issue:** #40
**Status:** implemented

---

## Problem

When LLM polish runs in generate mode and every polished segment is identical
to the corresponding raw MT segment, the final `.en.srt` is byte-for-byte
identical to `.raw.en.srt`.  Nothing in the pipeline's logs or returned
metadata makes that outcome explicit, so:

- Users cannot tell whether polish actually helped.
- Review and benchmark flows cannot distinguish improved vs unchanged outputs.
- Repeated no-op cases hide model quality problems and bad routing choices.
- Future automation cannot decide whether to retry with a different model or
  skip polish entirely.

`subtitle_pipeline.py` already has a `no_change` concept for the standalone
corrector path; generate mode lacked an equivalent signal.

## Scope

**In scope:**
- `_compare_candidates(raw, polished) → dict` — pure helper, compares segment
  texts and returns `polish_status`, `segments_changed`, `segments_unchanged`
- `_log_polish_stats(stats)` — helper that emits appropriate `logger.info` /
  `logger.warning` messages based on the returned stats
- Wiring into every LLM-polish branch in `run_generate` (three strategies:
  `embedded_jp_mt`, `ja_audio_asr_mt`, `untagged_audio_asr_mt`)
- Adding `polish_status`, `segments_changed`, `segments_unchanged` to the
  metadata dict returned by `run_generate`
- Unit tests for `_compare_candidates` and integration tests for
  `run_generate` metadata

**Out of scope:**
- Changing the SRT written to disk (the final file is still written even when
  status is `no_change`; the point is to make the outcome explicit, not to
  suppress output)
- Adding a CLI flag or exit code based on `polish_status`
- Retrying with a different model automatically

## Design

### `_compare_candidates(raw, polished) → Dict[str, Any]`

Located in `orchestrator.py`, alongside `run_generate`.

```python
def _compare_candidates(
    raw: SubtitleCandidate,
    polished: SubtitleCandidate,
) -> Dict[str, Any]:
    ...
```

**Returns** a dict with three keys:

| Key | Type | Description |
|-----|------|-------------|
| `polish_status` | `str` | `"changed"` \| `"no_change"` \| `"fallback"` |
| `segments_changed` | `int` | Number of segments whose text changed |
| `segments_unchanged` | `int` | Number of segments whose text is identical |

**Logic:**

1. If `polished.meta.get("fallback")` is `True` → `polish_status = "fallback"`,
   `segments_changed = 0`, `segments_unchanged = len(raw.segments)`.
2. Otherwise iterate over paired segments:
   - Compare `raw_seg.text.strip()` to `polished_seg.text.strip()`.
   - Count changed / unchanged.
   - Add `abs(len(raw.segments) - len(polished.segments))` to `changed` as a
     length-mismatch safety guard.
3. If `changed == 0` → `polish_status = "no_change"`, else `"changed"`.

### `_log_polish_stats(stats)`

Emits log messages based on status:

- `"fallback"` → `logger.info` ("LLM polish: fallback (LLM unreachable/disabled) — N segment(s) passed through unchanged")
- `"no_change"` → `logger.warning` ("LLM polish produced no change — all N segment(s) identical to raw MT")
- `"changed"` → `logger.info` ("LLM polish: N changed, N unchanged")

### Metadata additions

`run_generate` now includes the following keys in its return dict **when LLM
polish was attempted** (i.e. `use_llm_polish` was True):

```json
{
  "polish_status": "changed" | "no_change" | "fallback",
  "segments_changed": <int>,
  "segments_unchanged": <int>
}
```

When LLM polish is not run (strategies `embedded_en`, `en_audio_asr`) or when
`no_llm=True`, the keys are absent.

## Acceptance criteria

See `acceptance/40-generate-mode-llm-polish-no-change.md`.

## Open questions at implementation time

- None.
