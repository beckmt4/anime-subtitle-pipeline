# dev-subtitle-pipeline-entrypoint

**Purpose:** Add a batch pipeline entrypoint (`subtitle_pipeline.py`) that
processes SRT files through `subtitle_corrector.py` with hash-based change
detection, skip logic, structured JSON lines logging, retry hints, and
well-defined exit codes.

**Used in:** Issue #37
**Tool:** Claude Code (claude-sonnet-4-6)

---

## Prompt

```
Add failure detection and logging to the subtitle pipeline entrypoint.

Requirements:

1. PROCESSING VERIFICATION
   - After subtitle_corrector.py writes its output file, compare input and
     output using a byte-level hash
   - If input hash == output hash, the file was not changed — this is a
     silent failure
   - Log it and do NOT overwrite the input file with an identical copy

2. FAILURE LOG
   - Write a JSON lines log at /mnt/user/videos/subtitle_pipeline.log
   - Each line: { "timestamp", "file", "status", "cues_in", "cues_out",
     "drift_count", "error" }
   - status "no_change" = Ollama ran but output is identical to input
   - status "failed" = exception thrown during processing
   - status "skipped" = output exists and is newer than input

3. EXIT CODES
   - Exit 0: all files processed or skipped cleanly
   - Exit 1: one or more files had status "failed"
   - Exit 2: one or more files had status "no_change"

4. RETRY HINT
   - For "no_change" files, add a "retry_with_model" field in the log
   - Metadata only — don't auto-retry

5. Print a final summary to stdout regardless of log.

Follow all coding rules. Track via GitHub issues. Check in to GitHub.
```

---

## Notes

**What worked:**
- Refactoring `correct_srt()` into `_run_correction()` shared by both
  `correct_srt()` (returns str) and `correct_srt_ex()` (returns (str, stats))
  preserves full backward compatibility while exposing the stats the pipeline needs.
- `CorrectionStats` as a `NamedTuple` rather than a dataclass keeps it
  lightweight and unpacks cleanly as a function return value.
- SHA-256 on the UTF-8 encoded string catches any whitespace or encoding
  difference; comparing the rendered SRT (not the raw input) is correct because
  `_render_srt` normalises `\N` → newline, so a round-trip on an unchanged file
  may still differ from the raw input bytes.

**Watch for:**
- The hash compares `raw_content` (the file as read) against `corrected_srt`
  (the rendered output). If the input SRT uses `\N` line breaks, the rendered
  output will normalise them, so the hash will differ even when no corrections
  were made. This is intentional — the corrector always normalises output, and
  any normalisation counts as a change.
- `output.mtime > input.mtime` for the skip check uses file system mtimes,
  which have 1-second granularity on some systems. Tests must set the future
  mtime explicitly (`os.utime`) rather than relying on `time.sleep`.
- Exit 1 takes priority over exit 2 when both failures and no_change occur
  in the same run.

**Recommended follow-up:**
- Add a `--watch` mode that polls the inbox directory.
- Add a `--dry-run` flag to subtitle_pipeline.py (currently only corrector has one).
- Consider making the log path configurable via `config.yaml` in addition to CLI.
