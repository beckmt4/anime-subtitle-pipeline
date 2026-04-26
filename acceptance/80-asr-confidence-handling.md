# Acceptance Mapping - Issue #80: ASR Confidence Handling

## Implemented

- ASR segment metadata now records available Faster-Whisper confidence signals:
  `avg_logprob`, `no_speech_prob`, and `compression_ratio`.
- `build_candidate_from_segments()` derives deterministic warning signals for:
  high no-speech probability, low average log probability, high compression
  ratio, very short/long segments, long gaps, repeated text, and low Japanese
  character ratio.
- ASR candidates expose `meta.asr_quality`, `meta.asr_quality_status`, and
  `meta.asr_low_confidence_segment_count`.
- Per-segment ASR warnings are stored under `segment.meta.asr.warnings`.
- ASR warning metadata is propagated through MT and LLM/constraint outputs.
- Generate metadata includes `asr_quality` and
  `asr_low_confidence_segment_count`.
- QC can emit `asr_low_confidence` and `asr_source_warning` findings when a
  generated line traces back to weak ASR input or ambiguous audio selection.
- `config.yaml` exposes ASR quality warning/fail thresholds under
  `asr.quality`.

## Tests

- `tests/test_asr_candidate.py`
  - clean ASR candidate metadata
  - weak ASR segment warnings
  - empty ASR fail status
- `tests/test_asr_quality_propagation.py`
  - ASR metadata propagation through MT
  - ASR warning passthrough into QC findings
- `tests/test_orchestrator.py`
  - generate metadata includes ASR quality summary/counts

## Out Of Scope

- Audio source separation.
- Speaker diarization.
- Perfect probabilistic confidence scoring.
- Human review queue UI.
