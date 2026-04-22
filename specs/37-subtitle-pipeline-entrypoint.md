# Spec — Issue #37: subtitle_pipeline entrypoint with failure detection

**Issue:** #37
**Status:** implemented

---

## Problem

`subtitle_corrector.py` corrects individual SRT files but provides no batch
runner, no skip logic, no hash verification, and no structured audit trail.
When Ollama silently returns unchanged text (all cues reverted by drift guard
or model returned input verbatim), the caller has no way to detect or retry.

## Scope

**In scope:**
- `subtitle_pipeline.py` — new CLI entrypoint and library
- `process_file()` — per-file processing with skip, hash, status, log
- `run_pipeline()` — batch runner with exit codes
- JSON lines pipeline log (configurable path, default `/mnt/user/videos/subtitle_pipeline.log`)
- `correct_srt_ex()` in `subtitle_corrector.py` — returns `(str, CorrectionStats)`
- `CorrectionStats` named tuple — `cues_in`, `cues_out`, `corrected`, `drift_reverted`
- `--output-dir`, `--model`, `--log`, `--batch-size`, `--timeout`, `--verbose`, `--drift-log` CLI args

**Out of scope:**
- Auto-retry on `no_change`
- Watching a directory for new files
- Changes to Ollama call structure or system prompt

## Design

### `CorrectionStats` (subtitle_corrector.py)

```python
class CorrectionStats(NamedTuple):
    cues_in: int
    cues_out: int
    corrected: int
    drift_reverted: int
```

### `correct_srt_ex()`

Same signature as `correct_srt()` but returns `(srt: str, CorrectionStats)`.
Both delegate to `_run_correction()`. `correct_srt()` backward-compat unchanged.

### `process_file()` logic

```
if output exists and is newer than input:
    status = "skipped"
else:
    read input, parse cues
    call correct_srt_ex()
    sha256(input) == sha256(output)?
        → status = "no_change"; DO NOT write output
    else:
        write output
        status = "ok"
    on exception:
        status = "failed"
append JSON line to pipeline log
return status
```

### Log entry schema

```json
{
  "timestamp": "2026-04-22T14:30:01+00:00",
  "file": "episode.srt",
  "status": "ok|skipped|no_change|failed",
  "cues_in": 847,
  "cues_out": 847,
  "drift_count": 3,
  "error": null,
  "retry_with_model": "llama3"  // only present on no_change
}
```

`cues_in`, `cues_out`, `drift_count` are `null` for `skipped` and `failed`.

### `run_pipeline()` exit codes

| Code | Meaning |
|------|---------|
| 0 | All files ok or skipped |
| 1 | One or more `failed` (takes priority over 2) |
| 2 | One or more `no_change`, no failures |

### Retry hint

`_FALLBACK_MODEL` map: `mistral → llama3`, `llama3 → qwen2.5:7b`, etc.
Unknown models fall back to `_DEFAULT_FALLBACK = "llama3"`.
Suggestion is metadata only — no auto-retry.

### Output file naming

- With `--output-dir PATH`: `PATH/<input_stem>.srt`
- Without: `<input_stem>.corrected.srt` beside the input file

## Acceptance criteria

See `acceptance/37-subtitle-pipeline-entrypoint.md`.
