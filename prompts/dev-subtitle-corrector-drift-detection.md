# dev-subtitle-corrector-drift-detection

**Purpose:** Add a semantic drift detection layer to an existing Ollama-based
subtitle grammar corrector. Validates every LLM-corrected cue before accepting
it and reverts drift-flagged cues to the raw original.

**Used in:** Issue #35
**Tool:** Claude Code (claude-sonnet-4-6)

---

## Prompt

```
Add a semantic drift detection layer to `subtitle_corrector.py`.

After each batch is corrected by Ollama, run these checks on every cue before
accepting the output:

1. NOUN CHANGE DETECTION
   - Extract capitalized words and quoted terms from the raw cue
   - If any are missing from the corrected cue, flag it as DRIFT
   - Threshold: any noun drop = immediate flag (nouns are non-negotiable)

2. LENGTH RATIO CHECK
   - If corrected text is more than 40% longer or 40% shorter than raw text
     (by word count), flag as DRIFT

3. FALLBACK BEHAVIOR
   - If a cue is flagged as DRIFT, use the raw cue text unchanged
   - Do NOT silently accept the LLM output for flagged cues

4. REPORTING
   - Track drift flags per file
   - At the end of processing, print a summary line:
     "[corrector] file.srt: 847 cues processed, 12 corrected, 3 drift-reverted"
   - Add a --verbose flag that prints each drift-reverted cue with a side-by-side diff
   - Add a --drift-log PATH arg that writes all drift events as JSON lines

Work should follow all the rules laid out in the README files.
All work should be tracked via GitHub issues.
Always check in work to GitHub.
```

---

## Notes

**What worked:**
- Pure function `check_drift(raw, llm)` returning `(bool, reason, detail)` is
  easy to unit test and keeps the drift logic separate from the Ollama integration.
- Running noun check before length check matches the "nouns are non-negotiable"
  requirement and produces cleaner reason strings.
- Using `set` for noun extraction makes the missing-noun check O(n) against
  a substring search in the corrected text, which is correct for single-word nouns.

**Watch for:**
- `_extract_nouns` will capture sentence-initial common words as "nouns" — this
  is intentional (spec says extract all capitalized words). On very short cues
  (1-2 words) the length ratio check will be very sensitive. Both are by design.
- `drift_log` path is opened in append mode so multiple runs accumulate events.

**Recommended follow-up:**
- Consider a `--drift-threshold` flag to tune the ±40% ratio at runtime.
- Consider filtering sentence-initial capitals (the first word after `.!?`) if
  false positives become noisy in practice.
