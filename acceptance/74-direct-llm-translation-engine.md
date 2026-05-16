# Acceptance Mapping - Issue #74: Direct Context-Aware LLM Translation Engine

## Implemented

- Added `LLMDirectTranslator` class in `mt.py`:
  - Calls a local Ollama-compatible endpoint (`llm.base_url` + `/api/generate`).
  - Translates each Japanese source cue directly to English without going through
    MarianMT.
  - Accepts a configurable context window (`translation.context_window_segments`)
    of surrounding source segments; the prompt marks the cue being translated with
    `>>` so the model outputs only the current segment.
  - Supports prompt modes `literal`, `natural_subtitle`, and `accuracy_first`
    (controlled by `translation.mode`).
  - Accepts an optional `baseline_candidate` (used by the `hybrid` engine path)
    and includes the baseline MarianMT translation in the prompt for reference.
  - Retries failed LLM requests up to two times before raising.
  - Validates Ollama payload shape and rejects malformed payloads.
  - Rejects non-English/CJK output and empty output, then fails safely.
  - Normalizes multi-line/model-labeled replies and accepts only the current
    segment translation line.
  - Returns a structured `SubtitleCandidate` whose segment timing is preserved
    exactly from the source candidate.
- Added `llm_translate.py` compatibility module exposing:
  - `LLMTranslator` alias
  - `LLMDirectTranslator`
  - `translate_candidate(...)` convenience API
- Translation metadata recorded in candidate `meta`:
  - `translation_engine` (`llm_direct`)
  - `translation_model` (LLM model name)
  - `translation_mode`
  - `translation_dialogue_profile`
  - `context_window_segments`
  - `llm_base_url`
  - `translation_fallback` / `fallback_engine` / `fallback_reason` if fallback
    to MarianMT was triggered.
- Per-segment `meta.source_text_ja` records the original Japanese source for
  downstream QC judge checks.
- `translate_candidate_jp_to_en()` wrapper selects `llm_direct` or `hybrid`
  routes when configured; fails safely by falling back to Marian with explicit
  fallback metadata.

## Tests

- `tests/test_translation_engine_selector.py`
  - LLM direct selector metadata
  - LLM direct fallback to Marian with explicit metadata
  - Hybrid baseline plus LLM output
  - Context window + previous accepted English sent in prompt
  - Only current-segment output accepted from multi-line/model-labeled responses
  - Deterministic fallback tests for timeout, empty, malformed, and non-English output
  - Invalid engine configuration raises `InvalidTranslationEngineError`

## Deferred

- Cloud translation endpoints.
- Hardware-specific quantization tuning for LLM direct throughput.
- Full human review UI for flagged lines.
