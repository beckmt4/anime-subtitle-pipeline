# Acceptance Mapping - Issue #79: Translation QC Judge

## Implemented

Translation faithfulness checks now run through a dedicated module:

- `translation_qc.py` (`run_translation_qc`)

The judge accepts:

- Japanese source candidate
- Optional literal English candidate
- Final English candidate
- Candidate metadata / config

and emits structured candidate-level + segment-level summaries:

- `candidate_id`
- `qc_status` (`pass|warn|fail`)
- `score` (0.0–1.0)
- `findings[]` (per-segment findings with source/literal/final text)
- `segment_results[]` (per-segment review requirement + status)

| Check | Violation type | Severity |
|---|---|---|
| Missing or empty final line | `missing_final_line` | fail |
| CJK characters remain in English output | `non_english_leakage` | warning |
| Major final/baseline length drift | `possible_omission`, `possible_added_meaning` | warn/fail (config-driven) |
| Final drops obvious literal terms/entities | `final_literal_entity_drift` | warn/fail (config-driven) |
| Register appears softened vs source/literal | `register_softened` | warning |
| Optional local-LLM judge findings | `<llm code>` | warning/fail |

Warn/fail behavior is configurable in `config.yaml` under `translation_qc`.

Generate mode now includes `translation_qc` metadata for translated outputs.
Benchmark candidate metadata now includes `translation_qc` summaries for
JP-source translated candidates.

## Tests

- `tests/test_translation_qc.py`
  - `test_translation_qc_pass_case`
  - `test_translation_qc_warn_case_for_possible_omission`
  - `test_translation_qc_fail_case_for_empty_final_line`
  - `test_translation_qc_uses_mocked_llm_judge`
- `tests/test_translation_qc_judge.py`
  - existing subtitle-QC translation warning coverage remains in place
