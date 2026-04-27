# Acceptance criteria — Issue #81: Add local model and hardware evaluation matrix

**Issue:** #81  
**Status:** met

## Criteria

- [x] Add `docs/model-hardware-evaluation.md`.
- [x] Define at least three local runtime profiles: current workstation
  (`rtx_4090_24gb`), larger single-machine local AI (`ai_workstation_96gb`),
  and multi-machine local processing (`multi_node`).
- [x] Define model tiers to test: small/dev (7–8B), 14B, 32B, 70B-class, and
  405B+ where supported.
- [x] Explain why benchmark evidence is required before scaling hardware
  (section: *Why hardware alone will not fix translation quality*).
- [x] Define what benchmark evidence counts as a quality improvement
  (section: *Quality bottleneck definition* — chrF ≥ +2, BLEU ≥ +1, WER
  non-increasing).
- [x] Define what benchmark evidence counts as a throughput bottleneck
  (section: *Throughput bottleneck definition* — > 4 h / episode, confirmed
  as inference-bound).
- [x] Document optional benchmark metadata fields (`hardware_profile`, `model`,
  `quantization`, `context_window`, `runtime_seconds`, `quality_summary`,
  `translation_engine`, `prompt_mode`, `notes`) and how they are captured in
  `benchmark_results.json`.
- [x] Add acceptance mapping under `acceptance/` (this file).

## Test evidence

Documentation-only change; no automated tests required.

## Notes

- Hardware purchasing recommendations and live pricing are explicitly out of
  scope.
- Cloud service comparisons are out of scope.
- The `ai_workstation` and `multi_node` `runtime.profile` config values are
  documented here as future additions; they are not yet implemented in
  `config.yaml`.
- Benchmark metadata fields are defined as a documentation contract.  Optional
  code-level support for embedding `benchmark_run` metadata in
  `benchmark_results.json` is deferred and tracked separately.
