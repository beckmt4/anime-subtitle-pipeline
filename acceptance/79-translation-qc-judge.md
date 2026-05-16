# Acceptance Mapping - Issue #79: Translation QC Judge

## Implemented

Translation judge heuristics are integrated directly into `subtitle_qc.run_qc()`
via a `_add_translation_judge_warnings()` helper in `subtitle_qc.py`.  When the
optional `candidate` parameter is provided, the following per-segment checks are
applied before the ASR-warning passthrough:

| Check | Violation type | Severity |
|---|---|---|
| CJK characters remain in English output | `translation_possible_untranslated` | warning |
| Translated cue is ≤ 30 % of source length (source ≥ 10 chars) | `translation_possible_omission` | warning |
| Translated cue is ≥ 3.5× longer than a short source (source ≤ 8 chars, output ≥ 40 chars) | `translation_possible_added_meaning` | warning |
| Adult-register Japanese markers present but no corresponding English markers under `live_action_adult` profile | `translation_possible_softened_adult_dialogue` | warning |

All checks are deterministic heuristics that require no external model or
network call.  They emit `warning`-severity violations so `pass_qc` is not
affected; the findings are included in the machine-readable QC summary for
downstream review tooling.

Source text used in the ratio checks is read from
`segment.meta["source_text_ja"]` (set by both MarianMT and LLM direct
translation engines) or `segment.meta["source_text"]` as a fallback.

The `translation_dialogue_profile` value is read from `candidate.meta` and
controls whether the softened-adult-dialogue check runs.

## Tests

- `tests/test_translation_qc_judge.py`
  - `test_qc_flags_possible_omission_for_short_translation`
  - `test_qc_flags_possible_added_meaning_for_overlong_translation`
  - `test_qc_flags_softened_adult_dialogue_for_live_action_profile`
  - `test_qc_flags_untranslated_output_when_cjk_present`

## Deferred

- Optional local LLM judge path behind config for semantic equivalence scoring.
- Named-entity drift detection between intermediate and final translation.
- Per-candidate `qc_status` / `score` aggregate field (findings are currently
  surfaced as violations in the existing QC summary schema).
- Full manual review UI.
