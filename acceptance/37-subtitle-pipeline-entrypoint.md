# Acceptance criteria — Issue #37: subtitle_pipeline entrypoint

**Issue:** #37
**Status:** met

---

## Criteria

### subtitle_corrector.py extensions
- [x] `CorrectionStats` named tuple with `cues_in`, `cues_out`, `corrected`, `drift_reverted`
- [x] `correct_srt_ex()` returns `(str, CorrectionStats)`
- [x] `correct_srt()` unchanged and backward-compatible (existing tests still pass)
- [x] Both `correct_srt()` and `correct_srt_ex()` delegate to shared `_run_correction()`
- [x] `CorrectionStats` and `correct_srt_ex` exported in `__all__`

### Processing verification
- [x] Input and output compared via SHA-256 byte-level hash
- [x] `no_change` status when hashes match
- [x] Output file NOT written on `no_change`
- [x] Output file NOT written on `failed`

### Skip logic
- [x] `skipped` when output exists and `output.mtime > input.mtime`
- [x] `correct_srt_ex` not called for skipped files
- [x] File IS processed when output is older than input

### Pipeline log
- [x] JSON lines format — one object per file
- [x] Fields: `timestamp`, `file`, `status`, `cues_in`, `cues_out`, `drift_count`, `error`
- [x] `cues_in`, `cues_out`, `drift_count` are `null` for `skipped` and `failed`
- [x] `error` is `null` for non-failed entries
- [x] Log appended across multiple files (not overwritten)
- [x] Log parent directory created if missing

### Retry hint
- [x] `retry_with_model` field present on `no_change` entries only
- [x] `mistral` maps to `llama3`
- [x] Unknown models fall back to `_DEFAULT_FALLBACK`
- [x] Field absent from `ok`, `skipped`, `failed` entries

### Exit codes
- [x] Exit 0 — all ok or skipped
- [x] Exit 1 — one or more `failed`
- [x] Exit 2 — one or more `no_change`, no failures
- [x] Exit 1 takes priority over exit 2 when both occur

### Summary line
- [x] `"Pipeline complete: N ok, N skipped, N failed, N no_change — see <logfile>"` printed to stdout
- [x] Summary printed regardless of individual file status

### CLI
- [x] Positional `files` argument (one or more SRT paths)
- [x] `--output-dir PATH`
- [x] `--model`
- [x] `--log PATH` (default `/mnt/user/videos/subtitle_pipeline.log`)
- [x] `--batch-size N`
- [x] `--timeout S`
- [x] `--verbose`
- [x] `--drift-log PATH`

### Tests
- [x] `test_writes_output_when_changed` — ok path writes file
- [x] `test_log_entry_ok` — ok log entry shape
- [x] `test_creates_output_dir_if_missing` — parent dir created
- [x] `test_skips_when_output_newer` — skipped when newer
- [x] `test_log_entry_skipped` — skipped log entry shape
- [x] `test_processes_when_output_older` — not skipped when older
- [x] `test_detected_when_hashes_match` — no_change on identical content
- [x] `test_log_entry_includes_retry_hint` — retry_with_model present on no_change
- [x] `test_mistral_fallback_is_llama3` — fallback model correct
- [x] `test_unknown_model_fallback_is_default` — unknown model → default fallback
- [x] `test_exception_returns_failed` — exception → failed status
- [x] `test_log_entry_failed` — error message in log
- [x] `test_no_output_written_on_failure` — no output file on failure
- [x] `test_exit_0_all_ok` — batch exit code 0
- [x] `test_exit_1_on_failed` — batch exit code 1
- [x] `test_exit_2_on_no_change` — batch exit code 2
- [x] `test_exit_1_takes_priority_over_2` — failure beats no_change
- [x] `test_summary_printed_to_stdout` — summary line present
- [x] `test_default_output_suffix` — .corrected.srt beside input
- [x] `test_log_appends_multiple_entries` — multiple files → multiple log lines
- [x] `test_same_text_same_hash` — hash helper
- [x] `test_different_text_different_hash` — hash helper
- [x] `test_returns_hex_string` — hash format

---

## Test evidence

Tests run: `pytest tests/test_subtitle_pipeline.py tests/test_subtitle_corrector.py -v`

**Result:** 41 tests passed (23 pipeline + 18 corrector)

Lint: `flake8 subtitle_pipeline.py subtitle_corrector.py --select=E9,F --extend-ignore=F401,F841`

**Result:** exit 0
