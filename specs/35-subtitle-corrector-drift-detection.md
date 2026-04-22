# Spec — Issue #35: subtitle_corrector semantic drift detection

**Issue:** #35
**Status:** implemented

---

## Problem

The Ollama correction step in `subtitle_corrector.py` can silently introduce
meaning changes — substituting nouns, names, or dramatically rewriting a cue —
without any validation. A grammar-only corrector must not change what a subtitle
says, only how it reads.

## Scope

**In scope:**
- `check_drift(raw, llm)` — pure function, returns `(is_drift, reason, detail)`
- `_extract_nouns(text)` — extracts capitalized words and quoted terms
- Integration into `correct_srt()` post-batch validation loop
- Summary line printed at end of every run
- `--verbose` CLI flag for per-cue diff output
- `--drift-log PATH` CLI flag for JSON-lines audit trail
- Unit tests for all new logic
- No changes to timing, SRT format, or Ollama call structure

**Out of scope:**
- NLP-based POS tagging (regex extraction only, per spec)
- Changing the system prompt
- Reprocessing drift-flagged cues with a stricter prompt

## Design

### `_extract_nouns(text: str) -> set[str]`

Extracts two classes of terms that must be preserved:

1. **Capitalized words** — `\b[A-Z][a-zA-Z]+\b` (2+ chars, starts with capital).
   Catches proper nouns, character names, place names. Intentionally includes
   sentence-initial words; false positives are acceptable (over-detection is safer
   than under-detection for the noun-preservation goal).

2. **Quoted terms** — content inside `"…"` or `'…'` (non-greedy). Catches item
   names, honorifics, and foreign terms authors explicitly quoted.

Returns a `set[str]`.

### `check_drift(raw: str, llm: str) -> tuple[bool, str, str]`

Returns `(is_drift, reason, detail)`:

- If texts are identical → `(False, "", "")` (no API call waste tracking)
- **Noun check**: for each noun in `_extract_nouns(raw)`, if noun not present
  (substring match, case-sensitive) in `llm` → `(True, "noun_change", noun)`
- **Length ratio**: `ratio = len(llm.split()) / len(raw.split())` (skip if raw
  has 0 words). If `ratio > 1.4` or `ratio < 0.6` →
  `(True, "length_ratio", f"{ratio:.2f}")`
- Otherwise → `(False, "", "")`

Noun check runs before length check (nouns are non-negotiable per spec).

### `DriftEvent` dataclass

```python
@dataclass
class DriftEvent:
    index: int
    raw: str
    llm: str
    reason: str   # "noun_change" | "length_ratio"
    detail: str   # noun string | ratio string
    timestamp: str  # ISO 8601
```

### `correct_srt()` signature additions

```python
def correct_srt(
    cues, model=None, batch_size=20, timeout=120,
    dry_run=False,
    verbose=False,         # new
    drift_log=None,        # new: Optional[str] path
    label="",              # new: filename label for summary line
) -> str
```

### Integration flow (per batch)

```
for each corrected cue in batch:
    is_drift, reason, detail = check_drift(raw_text, llm_text)
    if is_drift:
        revert to raw_text
        record DriftEvent
        stats.drift_reverted += 1
        if verbose: print side-by-side diff
    elif llm_text != raw_text:
        stats.corrected += 1
```

### Summary line

Printed unconditionally to stdout at end of `correct_srt`:

```
[corrector] {label}: {total} cues processed, {corrected} corrected, {drift_reverted} drift-reverted
```

### Drift log format (JSON lines)

One JSON object per line:

```json
{"timestamp": "2026-04-22T14:30:01", "index": 42, "raw": "...", "llm": "...", "reason": "noun_change", "detail": "carriage"}
```

## Acceptance criteria

See `acceptance/35-subtitle-corrector-drift-detection.md`.

## Open questions at implementation time

- None.
