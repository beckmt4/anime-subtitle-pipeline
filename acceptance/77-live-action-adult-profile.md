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
  > register; do not euphemize or sanitize direct content."
- The profile name is recorded in candidate `meta.translation_dialogue_profile`
  for all translation engines (Marian, LLM direct, hybrid) so downstream QC and
  review tooling can read it.
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
- The implementation does not bypass any model safety restrictions; it only
  guides the prompt to avoid unwanted sanitization of source content.

## Tests

- `tests/test_translation_engine_selector.py`
  - `test_live_action_adult_profile_updates_prompt_and_metadata`: verifies that
    `"Dialogue profile: live_action_adult"` and the anti-sanitize instruction
    appear in the captured prompt, and that
    `meta["translation_dialogue_profile"] == "live_action_adult"`.
- `tests/test_translation_qc_judge.py`
  - `test_qc_flags_softened_adult_dialogue_for_live_action_profile`: verifies
    that a source with adult-register Japanese (`セックスしよう`) and a
    euphemized English translation (`Let's do that.`) under the
    `live_action_adult` profile triggers the
    `translation_possible_softened_adult_dialogue` warning.

## Deferred

- UI-based manual review queue for flagged lines.
- Semantic (vector-similarity) register check to supplement lexical markers.
- Per-title or per-scene profile presets.
- Safety flag for illegal-content indicators (tracked separately).
