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
| Missing or empty final line | `possible_omission` | fail |
| CJK characters remain in English output | `cjk_leakage` | warning |
| Major final/baseline length drift | `possible_omission`, `added_meaning` | warn/fail (config-driven) |
| Final drops obvious literal terms/entities | `wrong_meaning` | warn/fail (config-driven) |
| Register appears softened vs source/literal | `register_softened` | warning |
| Optional local-LLM judge findings | `<llm code>` | warning/fail |

Warn/fail behavior is configurable in `config.yaml` under `translation_qc`.

Generate mode now includes `translation_qc` metadata for translated outputs.
Benchmark candidate metadata now includes `translation_qc` summaries for
JP-source translated candidates.

Generate-mode QC sidecar (`*.en.qc.json`) now persists both subtitle and
translation QC under a versioned schema:

- `schema_version: 2`
- `subtitle_qc`
- `translation_qc`
- `overall_qc_status`

Routing integration with downstream review dependencies now includes translation
QC status/counts:

- `translation_qc.warn` can trigger REVIEW (Issue #56 dependency)
- `translation_qc.fail` can trigger REJECT (Issue #22/#56 dependency)
- `candidate_score` includes translation QC status + warning/fail counts, and
  routing `triggered_by` records translation-QC drivers.

## Epic/dependency mapping update

- Parent epic `beckmt4/anime-subtitle-pipeline#73`: translation QC findings are
  now persisted and enforced in generate-mode routing.
- Review-routing dependencies `#22` and `#56`: translation-QC-driven REVIEW/REJECT
  triggers are now available in policy routing output.
- Taxonomy standardization (`feat: add translation failure taxonomy and per-line error tagging`):
  translation findings now normalize to canonical codes from
  `core/quality/failure_taxonomy.py`, include per-line `failure_codes`, expose
  `taxonomy_codes` in translation QC outputs, and benchmark reports include
  `translation_failure_taxonomy` aggregate counts.

## Tests

- `tests/test_translation_qc.py`
  - `test_translation_qc_pass_case`
  - `test_translation_qc_warn_case_for_possible_omission`
  - `test_translation_qc_fail_case_for_empty_final_line`
  - `test_translation_qc_uses_mocked_llm_judge`
- `tests/test_translation_qc_judge.py`
  - existing subtitle-QC translation warning coverage remains in place
