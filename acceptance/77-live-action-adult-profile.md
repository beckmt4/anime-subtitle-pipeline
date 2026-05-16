# Acceptance Mapping - Issue #77: Live-Action and Adult-Dialogue Translation Profile

## Implemented

- Added `translation.dialogue_profile` config key in `config.yaml` (values:
  `default` | `live_action_adult`; default is `default`).
- Added `Config.translation_dialogue_profile` property accessor in `config.py`.
- Added `VALID_DIALOGUE_PROFILES` set and `_validate_dialogue_profile()` helper
  in `mt.py`; unknown profiles fall back to `default` with a warning instead of
  crashing the pipeline.
- `LLMDirectTranslator` reads the dialogue profile and appends an explicit
  instruction to the prompt when `live_action_adult` is active:
  > "For live-action/adult dialogue, preserve explicit sexual/profane wording and
  > register; do not euphemize or sanitize explicit content, and do not add
  > sexual content not present in the source."
- Added `translation.profiles.live_action_adult` preset in `config.yaml`:
  - `engine: llm_direct`
  - `workflow: literal_then_natural`
  - `mode: accuracy_first`
  - `context_window_segments: 6`
  - `preserve_adult_register: true`
  - `flag_low_confidence: true`
  - `flag_high_risk_content: true`
  The preset is auto-applied when `translation.dialogue_profile` is
  `live_action_adult`.
- The profile name is recorded in candidate `meta.translation_dialogue_profile`
  for all translation engines (Marian, LLM direct, hybrid) so downstream QC and
  review tooling can read it.
- Translation metadata now also records
  `translation_preserve_adult_register`,
  `translation_flag_low_confidence`, and
  `translation_flag_high_risk_content`.
- Translation QC judge in `subtitle_qc.py` checks for softened adult dialogue
  when `translation_dialogue_profile == "live_action_adult"`: if the Japanese
  source contains known adult-register markers but the English output does not
  contain corresponding markers, a `translation_possible_softened_adult_dialogue`
  warning is emitted.

## Safety behavior

- The profile instructs the model to translate *accurately* and not to
  *add* explicit content not present in the source.
- The QC judge flags cases where adult-register source text appears to have been
  softened or euphemized, so a human reviewer can verify the translation.
- The prompt asks the model to emit `[LOW_CONFIDENCE]` instead of guessing for
  uncertain lines, and QC raises `translation_low_confidence_flagged` warnings.
- QC raises `translation_high_risk_content_review` warnings for indicators of
  potentially illegal or coercive/minor-related material, routing these lines to
  manual review.
- The implementation does not bypass any model safety restrictions; it only
  guides the prompt to avoid unwanted sanitization of source content.

## Tests

- `tests/test_translation_engine_selector.py`
  - `test_live_action_adult_profile_updates_prompt_and_metadata`: verifies that
    `"Dialogue profile: live_action_adult"` and anti-sanitize/anti-invention plus
    review-marker instructions appear in the prompt, and that preset-driven
    metadata (`translation_engine`, `context_window_segments`,
    `translation_flag_low_confidence`, `translation_flag_high_risk_content`) is
    set.
- `tests/test_translation_qc_judge.py`
  - `test_qc_flags_softened_adult_dialogue_for_live_action_profile`: verifies
    that a source with adult-register Japanese (`セックスしよう`) and a
    euphemized English translation (`Let's do that.`) under the
    `live_action_adult` profile triggers the
    `translation_possible_softened_adult_dialogue` warning.
  - `test_qc_flags_low_confidence_marker_for_review`: verifies uncertain output
    markers are surfaced as `translation_low_confidence_flagged`.
  - `test_qc_flags_high_risk_content_for_manual_review`: verifies
    coercion/minor-risk indicators are surfaced as
    `translation_high_risk_content_review`.

## Deferred

- UI-based manual review queue for flagged lines.
- Semantic (vector-similarity) register check to supplement lexical markers.
- Per-title or per-scene profile presets.
