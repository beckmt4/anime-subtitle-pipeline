# Benchmark Mode Quick Reference (Generalized)

## What It Does
Generates and compares ALL available English subtitle candidates derived from:

- Embedded EN subtitle streams
- Embedded JP subtitle streams → Machine Translation (→ optional LLM polish)
- EN audio tracks → ASR
- JP audio tracks → ASR → MT (→ optional LLM polish)

Supports multi-track inputs, smart reference selection via priority list, and optional full pairwise comparison matrix.

## Minimum Requirements

At least one of the following present in the media:

- EN subtitle track (text-based)
- JP subtitle track (text-based)
- EN audio track
- JP audio track

Recommended for richest comparison: Both EN & JP audio plus both subtitle languages.

## CLI Usage

```bash
python main.py video.mkv --mode benchmark              # Standard run
python main.py video.mkv --mode benchmark --no-llm     # Skip LLM polish
python main.py video.mkv --list-tracks                 # Inspect streams first
```

## Output

Creates `outbox/benchmark_results.json` containing:

- `reference_id`: Chosen reference candidate (priority-based)
- `candidates`: All generated EN candidates with metadata
- `comparisons`: Reference comparisons plus optional pairwise matrix
- Metrics per comparison (WER, BLEU, chrF) + truncated diffs list

## Candidate Types (IDs contain source cues)

- `embedded_en_sX` – Direct embedded English subtitle track
- `embedded_jp_mt[_llm]_sY` – JP subtitle → MT (→ optional LLM)
- `en_audio_asr_aN` – EN audio track → ASR
- `ja_audio_asr_mt[_llm]_aM` – JP audio → ASR → MT (→ optional LLM)

## Metrics Explained

| Metric | Range | Better | Meaning |
|--------|-------|--------|---------|
| **WER** | 0.0 - 1.0+ | Lower | Word Error Rate (0.0 = perfect match) |
| **BLEU** | 0 - 100 | Higher | Translation quality (100 = perfect) |
| **chrF** | 0 - 100 | Higher | Character-level similarity (100 = perfect) |

## Example Comparison Summary (abbreviated)

```text
Benchmark Summary (reference = embedded_en_s10):
  en_audio_asr_a0 vs embedded_en_s10: WER=14.2%, BLEU=72.3, chrF=84.1
  en_audio_asr_a1 vs embedded_en_s10: WER=15.9%, BLEU=70.8, chrF=83.5
  ja_audio_asr_mt_llm_a2 vs embedded_en_s10: WER=31.7%, BLEU=46.2, chrF=66.4
  embedded_jp_mt_llm_s11 vs embedded_en_s10: WER=28.5%, BLEU=50.1, chrF=69.2
```

Enable pairwise matrix (`compare_all_pairs: true`) to see all remaining cross-source comparisons.

## Configuration Snippet (`config.yaml`)

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
  compare_all_pairs: false          # set true for full matrix
  max_diffs_per_comparison: 20      # truncate diff list
  metrics:                          # (currently always computed)
    compute_wer: true
    compute_bleu: true
    compute_chrf: true
```

## Common Issues & Tips

**Missing candidates** – Check `--list-tracks` output; ensure text-based (non-bitmap) subtitles.

**BLEU = 0** – Normal for very short / dissimilar segments; rely more on WER + chrF.

**Large WER** – May indicate segmentation drift (ASR chunking vs subtitle timing); inspect diff samples.

**Performance slow** – Disable LLM polish or pairwise matrix; reduce active sources.

**Reference unexpected** – Adjust `reference_priority` ordering.

## Testing

Run comparison logic tests:

```bash
python test_benchmark.py
```

Run generalized orchestration tests:

```bash
python test_benchmark_generalized.py
```

## Next Steps

See `BENCHMARK_IMPLEMENTATION.md` for full architecture, evolution notes, and enhancement roadmap.
