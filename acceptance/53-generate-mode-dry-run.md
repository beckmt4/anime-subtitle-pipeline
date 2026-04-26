# Acceptance criteria — Issue #53: Add generate-mode dry-run / inspect-only flow

**Issue:** #53
**Status:** met

## Criteria

- [x] generate mode exposes an inspect-only entry path via the `--dry-run` CLI
  flag and the `run_generate_inspect` function in `orchestrator.py`

- [x] inspect-only mode performs discovery and strategy evaluation but does not
  invoke ASR, MT, LLM polish, mux, or final output writes; verified by
  `tests/test_orchestrator_inspect.py::TestNoHeavyCallsInInspectMode`

- [x] inspect-only mode returns structured metadata that identifies the planned
  strategy, discovered sources, quality risk, probe requirement, and expected
  artifact paths; verified by schema tests in
  `tests/test_orchestrator_inspect.py`

- [x] tests verify that heavy runtime calls (ASR, MT, LLM, file writes) are not
  made in inspect-only mode; see `TestNoHeavyCallsInInspectMode`

- [x] tests cover representative source layouts: embedded EN, embedded JP+MT,
  JA audio ASR+MT, EN audio ASR, untagged audio fallback, and no-source
  failure; see `TestInspectStrategySelection`

- [x] implementation adds tests under `tests/test_orchestrator_inspect.py`

- [x] acceptance criteria are documented in `acceptance/53-generate-mode-dry-run.md`

## Inspect result schema

```python
{
  "inspect_only": True,                 # sentinel: no execution occurred
  "video": "<filename>",
  "planned_strategy": "<strategy>",     # None when no source found
  "no_source": bool,
  "sources_detected": {
    "en_sub_idx": int | None,
    "ja_sub_idx": int | None,
    "en_audio_order": int | None,
    "ja_audio_order": int | None,
  },
  "audio_streams": [                    # per-stream descriptors
    {"order": int, "index": int, "codec": str, "language": str | None,
     "channels": int | None, "sample_rate": int | None},
    ...
  ],
  "subtitle_streams": [
    {"order": int, "index": int, "codec": str, "language": str | None,
     "is_bitmap": bool},
    ...
  ],
  "selection_report": {                 # same schema as run_generate (issue #52)
    "selected_source": str,
    "confidence_tier": "high"|"medium"|"low"|"very_low",
    "rationale": str,
    "sources_evaluated": [...],
    "overrides_active": [...],
    "review_recommended": bool,
    "review_reason": str | None,
  } | None,
  "artifact_plan": {                    # expected output paths for a real run
    "final_srt": str,
    "qc_json": str,
    "raw_srt": str,                     # only for MT strategies
  },
  "quality_risk": {
    "confidence_tier": str,
    "review_likely": bool,
    "probe_required": bool,
    "heuristic_fallback": bool,
    "heuristic_fallback_reason": str,   # only when heuristic_fallback=True
  },
  "probe_required": bool,               # True when Whisper probe would be needed
  "probe_note": str | None,            # explanation when probe_required=True
  "formatting_artifact_risk": bool,     # True for ASS/SSA/WebVTT embedded subs
  "formatting_artifact_note": str | None,
}
```

## Test evidence

All tests in `tests/test_orchestrator_inspect.py` pass without requiring
any live services (no ASR model, no MT model, no LLM, no ffmpeg).

Run:
```
python -m pytest tests/test_orchestrator_inspect.py -v
```

## Notes

- The selection report schema is intentionally identical to that returned by
  `run_generate`, keeping it aligned with the explainability work from #52.
- The language probe (`_probe_audio_language`) is **not** called in inspect
  mode.  When a probe would be required, `probe_required=True` and
  `probe_note` explains the ambiguity.  The `planned_strategy` reflects the
  decision tree evaluated without probe input (i.e., assuming container tags
  are correct or the untagged fallback).
- OCR source handling is out of scope (bitmap subtitle streams are detected
  and listed but not inspected for content).
- Benchmark-mode dry runs are out of scope.
