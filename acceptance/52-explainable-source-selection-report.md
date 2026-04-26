# Acceptance: #52 Explainable Source-Selection Report

## Behavior

- [x] `run_generate()` returns a structured `selection_report` in metadata.
- [x] The report includes `selected_source`, `confidence_tier`, `rationale`,
      `sources_evaluated`, `overrides_active`, `review_recommended`, and
      `review_reason`.
- [x] Each evaluated source records detection state, stream reference, status,
      and the reason it was selected, skipped, or unavailable.
- [x] Untagged and probe-rerouted audio cases are visible in the report.
- [x] Low-confidence MT/fallback paths recommend review.

## Tests

- [x] `test_selection_report_embedded_en_high_confidence`
- [x] `test_selection_report_embedded_jp_mt_low_confidence_review_recommended`
- [x] `test_selection_report_mt_strategy_low_confidence_review_recommended`
- [x] `test_selection_report_untagged_audio_fallback`
- [x] `test_generate_no_usable_source_error_case`
- [x] `test_selection_report_skip_embedded_en_override`
- [x] `test_selection_report_audio_track_override`
- [x] `test_selection_report_probe_reroute_reflected`

## Notes

The explainability record is returned in process metadata and logged by
`_log_selection_report()`. Persistent database storage and UI rendering are
intentionally left to later review/persistence work.
