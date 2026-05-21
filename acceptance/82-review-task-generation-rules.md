# Acceptance criteria — Issue #82: Review-task generation rules for weak generate/benchmark outputs

**Issue:** #82  
**Status:** met

## Criteria

- [x] review-task generation rules are defined for generate-mode outputs
- [x] review-task generation rules are defined for benchmark-mode outputs
- [x] low-confidence and heuristic-fallback outcomes can be promoted to `review_required` by deterministic rules
- [x] the rules define stable reason codes or categories for why a task was created
- [x] the minimum review-task payload is documented and testable
- [x] tests cover at least one generate-driven and one benchmark-driven review-routing case
- [x] implementation adds or updates tests under `tests/`
- [x] acceptance criteria are mapped in `acceptance/`

## Test evidence

- `python -m pytest tests/test_review_task_routing.py tests/test_orchestrator.py tests/test_benchmark_generalized.py -v --tb=short`
- `python -m pytest -v --tb=short -m "not integration"`
- `python -m flake8 media_inspect.py compare_core.py config.py models.py orchestrator.py llm_polish.py srt_writer.py audio_utils.py subtitle_utils.py asr.py mt.py tracing.py batch_process.py benchmark.py core/review/routing.py tests/test_review_task_routing.py --select=E9,F --extend-ignore=F401,F841 --exclude venv`

## Notes

- Rules use subtitle QC findings plus confidence/routing signals for generate-mode escalation.
- Invalid or zero-cue SRT outputs are never routed as normal success.
- Benchmark routing marks weak metric outcomes (WER/BLEU/chrF threshold breaches) as review-required, while single-candidate/no-comparison cases remain warnings.
