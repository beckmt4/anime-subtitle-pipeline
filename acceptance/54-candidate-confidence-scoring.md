# Acceptance Mapping - Issue #54: Candidate Confidence Scoring

## Implemented

- Generate mode already emits `candidate_score` with:
  - total score
  - grade
  - contributing factors
- Candidate scoring now includes an ASR warning-density penalty based on QC
  findings:
  - `asr_low_confidence`
  - `asr_source_warning`
- Candidate score metadata includes:
  - `asr_warning_count`
  - `asr_warning_density`
- Policy routing now sends outputs to review when ASR warning density reaches
  `policy.routing.asr_warning_review_density`.
- Default review threshold is `0.10`, so outputs with ASR warnings on 10% or
  more of cues are not auto-passed.
- SRT writer now enforces `subtitles.min_gap_sec` so generated SRT files do not
  retain overlapping adjacent cues after duration extension/splitting.
- Natural LLM polish prompt now explicitly forbids adding ideas, dramatizing, or
  inferring missing context.

## Tests

- `tests/test_asr_warning_routing.py`
  - ASR warning density reduces candidate score
  - high ASR warning density routes to review
- `tests/test_srt_writer_overlap.py`
  - overlapping cues are clamped before writing
  - min-duration extension does not create final SRT overlaps
- Existing generate-mode scoring and policy tests continue to pass.

## Validation

- `venv/bin/python -m pytest -m 'not integration'`

## Notes

The ABW-043 run that motivated this work had roughly 25% ASR warning density
(`238 / 946` cues), which now receives the full ASR-density score penalty and
routes to REVIEW.
