# Acceptance: #53 Generate Inspect-Only Flow

## Behavior

- [x] Generate mode exposes an inspect-only path through
      `run_generate(..., inspect_only=True)` and CLI `--inspect-only`.
- [x] Inspect-only performs media source discovery and strategy evaluation.
- [x] Inspect-only returns structured metadata with `strategy`,
      `selection_report`, `planned_output_srt`, and `planned_qc_json`.
- [x] Inspect-only marks `inspect_only=True` and `executed=False`.
- [x] Inspect-only does not open the artifact registry or create registry runs.
- [x] Inspect-only does not run subtitle extraction, audio extraction, ASR, MT,
      LLM polish, QC, muxing, or output writes.

## Tests

- [x] `test_inspect_only_embedded_en_skips_execution_calls`
- [x] `test_inspect_only_embedded_jp_mt_skips_mt_llm_and_writes`
- [x] `test_inspect_only_ja_audio_skips_asr_mt_llm_and_writes`
- [x] `test_inspect_only_untagged_audio_uses_heuristic_without_probe`
- [x] `test_inspect_only_no_usable_source_error_case`

## Notes

Inspect-only intentionally skips language probing because probing instantiates
ASR machinery. Plans are based on container metadata plus the existing untagged
audio heuristic, and the returned `selection_report` is the same explainability
schema used by executed generate runs.
