# Benchmark Mode Implementation Summary (Generalized)

## Evolution

The benchmark mode has been generalized from an initial minimal design (single embedded EN reference + two candidates) to a multi-track, multi-source system capable of evaluating every available English subtitle candidate derived from:

- Embedded EN subtitle streams
- Embedded JP subtitle streams → MT (→ optional LLM polish)
- EN audio tracks → ASR
- JP audio tracks → ASR → MT (→ optional LLM polish)

It supports multiple tracks per type, smart reference selection via configurable priority, and optional full pairwise comparison matrices.

## Core Modules

### `compare_core.py`

Unchanged from the minimal phase – provides alignment and metric computation:

- `align_segments(ref, cand)` – temporal alignment (max overlap strategy, many-to-one tolerant)
- `compute_metrics(ref_texts, cand_texts)` – WER (jiwer), BLEU & chrF (sacrebleu)
- `compare_candidates(ref, cand, diff_threshold)` – orchestrates alignment + metrics + diff extraction

### `benchmark.py` (Generalized)

New capabilities:

1. Multi-track discovery (`find_all_tracks_by_language`) for audio & subtitles (EN + JP)
2. Comprehensive candidate generation loops for each enabled source category
3. Reference selection (`select_reference_candidate`) using ordered priority list in config
4. Comparison phase:

- Always: all non-reference candidates vs reference
- Optional: full pairwise comparisons across all candidates (`compare_all_pairs: true`)

- Output structure updated: `reference_id`, full candidate metadata list, aggregated comparisons array (may include duplicates when pairwise enabled)

### New Test File `test_benchmark_generalized.py`

Adds deterministic tests for generalized logic using monkeypatch stubs (no ffmpeg / ASR / MT calls):

- Generation & reference selection across multiple tracks
- Fallback reference logic when primary source absent
- Pairwise matrix size validation

## Configuration (`config.yaml` benchmark section)

```yaml
benchmark:
  sources:
    use_embedded_en: true
    use_embedded_jp: true
    use_en_audio: true
    use_ja_audio: true
  reference_priority:
    - embedded_en
    - en_audio_asr
    - ja_audio_asr_mt
    - embedded_jp_mt
  compare_all_pairs: false
  max_diffs_per_comparison: 20
  metrics:               # (present; current code always computes all)
    compute_wer: true
    compute_bleu: true
    compute_chrf: true
```

### Reference Priority Semantics

The first candidate whose `id` contains one of the ordered tokens becomes the reference. This enables flexible experimentation (e.g., promote ASR output to reference by moving `en_audio_asr` earlier).

## Output Structure (Generalized Example)

```json
{
  "video": "sample.mkv",
  "reference_id": "embedded_en_s10",
  "candidates": [
    {"id": "embedded_en_s10", "source": "embedded", "language": "en", "segment_count": 120, "origin_stream": "sub:10"},
    {"id": "embedded_jp_mt_llm_s11", "source": "embedded_mt_llm", "language": "en", "segment_count": 118},
    {"id": "en_audio_asr_a0", "source": "asr", "language": "en", "segment_count": 125, "origin_stream": "audio:0"},
    {"id": "en_audio_asr_a1", "source": "asr", "language": "en", "segment_count": 124, "origin_stream": "audio:1"},
    {"id": "ja_audio_asr_mt_llm_a2", "source": "asr_mt_llm", "language": "en", "segment_count": 130, "origin_stream": "audio:2"}
  ],
  "comparisons": [
    {"ref_id": "embedded_en_s10", "cand_id": "en_audio_asr_a0", "metrics": {"wer": 0.14, "bleu": 72.3, "chrf": 84.1}, "num_diffs": 34, "diffs": [...]},
    {"ref_id": "embedded_en_s10", "cand_id": "en_audio_asr_a1", ...},
    {"ref_id": "embedded_en_s10", "cand_id": "ja_audio_asr_mt_llm_a2", ...},
    {"ref_id": "embedded_en_s10", "cand_id": "embedded_jp_mt_llm_s11", ...},
    {"ref_id": "en_audio_asr_a0", "cand_id": "en_audio_asr_a1", ...},
    {"ref_id": "en_audio_asr_a0", "cand_id": "ja_audio_asr_mt_llm_a2", ...},
    ... (pairwise matrix continues)
  ]
}
```

Note: When `compare_all_pairs` is `true`, comparisons against the reference are duplicated in pairwise listings (design acceptable for exploratory analysis; downstream tooling can deduplicate if desired).

## Alignment Strategy Recap

- Primary: Maximum temporal overlap per reference segment
- Tie-breaking: Nearest midpoint when no overlap candidates
- Many-to-one: Permitted; metrics treat candidate segment text once per aligned pair

## Metric Interpretation

- WER: Sensitive to tokenization and punctuation normalization (jiwer default chain)
- BLEU: Can be 0 on short or highly dissimilar segments (expected behavior)
- chrF: More stable for short subtitles; complements BLEU

## Performance Considerations

- Multi-track extraction increases I/O (each audio track demux + ASR pass)
- Optional LLM polishing doubles processing for MT-derived candidates; disable via `--no-llm` for faster baseline runs
- Pairwise matrix scales O(N²); use only when necessary for cross-candidate comparative research

## Testing Overview

Minimal comparison logic tests remain (`test_benchmark.py`). Generalized orchestration covered by `test_benchmark_generalized.py` with monkeypatched environment (no external tooling).

## Future Enhancements (Next Iteration Targets)

1. Honor metric toggles in config (compute_wer/compute_bleu/compute_chrf).
2. Add aggregate summary table (per-source averages, variance metrics).
3. Provide HTML/Markdown report renderer with color-coded diff highlights.
4. Introduce normalization pipeline (case folding, punctuation control) selectable via config.
5. Caching for ASR/MT intermediate artifacts keyed by audio/sub stream hash.
6. Add source confidence metadata (e.g., ASR average probability) to candidates.
7. Optional pruning of near-duplicate segments before metric computation.

## File Changes Summary (Generalized Phase)

- `benchmark.py` rewritten for multi-track candidate generation and pairwise comparison capability.
- `test_benchmark_generalized.py` added for orchestration tests.
- Documentation (this file + quickstart) updated to reflect new functionality.

## Backwards Compatibility

- CLI invocation unchanged (`--mode benchmark`).
- Existing environments without JP tracks still produce meaningful results (EN-only path).
- Output JSON extended, not breaking previous keys (`video`, `candidates`, `comparisons`).

## Usage Examples

Basic run:

```bash
python main.py video.mkv --mode benchmark
```

Disable LLM polish:

```bash
python main.py video.mkv --mode benchmark --no-llm
```

Enable pairwise comparisons (edit config or inline patch):

```yaml
benchmark:
  compare_all_pairs: true
```

## Validation Checklist

✅ Multi-source discovery
✅ Candidate generation (EN + JP derived)
✅ Reference priority selection
✅ Reference comparisons
✅ Optional pairwise matrix
✅ Diff truncation (`max_diffs_per_comparison`)
✅ Documentation updated

## Known Limitations

- Metric toggles currently not enforced (all metrics always computed).
- Pairwise comparisons duplicate reference pair entries.
- Bitmap subtitle OCR not implemented.
- No persistence/caching of ASR/MT intermediate artifacts.

---
This document supersedes the earlier minimal benchmark summary; historical context retained here as part of evolution notes.
