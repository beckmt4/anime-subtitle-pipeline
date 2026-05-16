# Acceptance Mapping — Literal-First / Natural-Subtitle Second-Pass Workflow

Parent epic: beckmt4/anime-subtitle-pipeline#73

## Implemented

### Config

- Added `translation.workflow` config key in `config.yaml`:
  - `"single_pass"` (default) — existing single-pass translate + polish behaviour.
  - `"literal_then_natural"` — two-pass workflow (Pass 1 literal, Pass 2 natural).
- Added `translation.save_intermediate` config key (default `false`).
  - When `true`, the literal-pass segment texts and timing are stored in the final
    candidate's `meta["literal_pass_segments"]` for traceability and debugging.
- Added `Config.translation_workflow` property accessor in `config.py`.
- Added `Config.translation_save_intermediate` property accessor in `config.py`.
- Added `natural_from_literal` LLM prompt style in `config.yaml` under
  `llm.prompts`.  The prompt instructs the LLM to adapt a literal translation into
  natural subtitle English while preserving exact meaning, names, and register.

### Translation engine — `mt.py`

- Added `VALID_TRANSLATION_WORKFLOWS = {"single_pass", "literal_then_natural"}`.
- Updated `_translation_config()` to read `workflow` and `save_intermediate` from
  the `translation` config section.
- Added `run_two_pass_translation(candidate, config, ...)` function:
  - **Pass 1**: calls `translate_candidate()` using the configured engine.
    Sets `translation_pass = "literal"` in the literal candidate meta.
  - **Pass 2**: calls `adapt_candidate_from_literal()` (see below) to produce the
    natural subtitle candidate.
  - Records `translation_workflow`, `literal_pass_candidate_id` in final meta.
  - Stores `literal_pass_segments` when `save_intermediate=True`.
  - Timing is never changed; segment `start`/`end` always come from the source.

### Natural adaptation — `llm_polish.py`

- Added `LLMPolisher.adapt_candidate_from_literal(literal_candidate, ja_candidate)`
  method:
  - Uses `polish_text()` with `style="natural_from_literal"`.
  - Japanese source segments passed as LLM context when segment counts match.
  - **Drift guard**: per-segment check comparing natural output vs literal input.
    Diverging segments revert to the literal text with
    `two_pass_qc_warning = "drift_reverted_to_literal:<reason>"` in segment meta.
  - **Stock-phrase collapse guard**: if LLM collapses all segments into one known
    filler phrase, entire batch reverts to literal and candidate meta records
    `two_pass_qc_warning = "stock_phrase_collapse_reverted_to_literal"`.
  - LLM-disabled / unreachable fallback: returns literal text unchanged with
    `fallback = True` in candidate meta.
  - Records `two_pass_adapt_stats` (`total`, `polished`, `reverted`, `unchanged`).
  - Result candidate `source = "two_pass_llm"`, ID = `<literal_id>_natural`.
- Added `adapt_candidate_from_literal(literal_candidate, config, ja_candidate)`
  convenience wrapper (module-level function).

### Metadata linking

All three passes are traceable in the final candidate:

| Key | Carrier | Value |
|---|---|---|
| `translation_pass` | literal candidate meta | `"literal"` |
| `translation_workflow` | final candidate meta | `"literal_then_natural"` |
| `literal_pass_candidate_id` | final candidate meta | ID of literal candidate |
| `literal_pass_segments` | final candidate meta | `[{start, end, text}, …]` (opt.) |
| `literal_text` | adapted segment meta | Original literal text for changed segs |
| `two_pass_adapt_stats` | final candidate meta | `{total, polished, reverted, unchanged}` |
| `two_pass_qc_warning` | candidate / segment meta | Drift revert or collapse message |

## Tests

- `tests/test_two_pass_translation.py`
  - **Config accessors**: `translation_workflow` and `translation_save_intermediate`
    defaults and YAML-read values.
  - **`adapt_candidate_from_literal`** method:
    - Adapted text replaces literal in segments.
    - Timing always preserved from literal candidate.
    - Output ID, source, meta fields.
    - `natural_from_literal` style used.
    - Japanese context forwarded; mismatched segment count falls back to empty.
    - Empty candidate handled cleanly.
  - **Drift guard (QC warning)**: noun-drop and severe compression revert to
    literal with `two_pass_qc_warning`; acceptable naturalisation accepted.
  - **Stock-phrase collapse guard**: collapse reverts all segments with warning;
    non-collapsing batch unaffected.
  - **LLM fallback**: disabled / unreachable LLM returns literal text unchanged.
  - **Convenience wrapper**: `adapt_candidate_from_literal` delegates and forwards
    `ja_candidate`.
  - **`run_two_pass_translation` orchestration**: translate called before adapt;
    source candidate passed to translate; literal result passed to adapt; literal
    pass marked with `translation_pass = "literal"`.
  - **Timing**: segment start/end unchanged in final output.
  - **`save_intermediate`**: segments stored / not stored based on flag; timing
    preserved in stored segments.
  - **`VALID_TRANSLATION_WORKFLOWS`** constant coverage.

## Docs

- `docs/two-pass-translation-workflow.md` — explains single-pass vs two-pass,
  when to use each, config reference, candidate metadata, and API usage.

## Deferred

- Wiring `translation.workflow` into `orchestrator.run_generate` so the pipeline
  auto-selects two-pass when configured (currently `run_two_pass_translation` must
  be called explicitly).
- Human review UI for surfacing `two_pass_qc_warning` segments.
- Optional Pass 3 QC comparison (Japanese vs literal vs final scoring).
- Per-profile workflow selection (e.g. `live_action_adult` auto-enables two-pass).
