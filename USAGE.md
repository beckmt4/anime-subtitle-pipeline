# Usage Guide

## Modes Overview

| Mode | Purpose | Entry Function |
|------|---------|----------------|
| generate | Produce best English subtitles via strategy selection | orchestrator.run_generate |
| benchmark | Produce and compare all English subtitle candidates | orchestrator.run_benchmark |
| subtitle | Legacy JP audio → ASR → MT → (LLM) pipeline | process_video (main.py) |

## Generate Mode

Automatically selects the optimal source path:
1. Embedded English subtitles
2. English audio → ASR
3. Japanese subtitles → MT (→ LLM)
4. Japanese audio → ASR → MT (→ LLM)

Configuration (config.yaml):
```yaml
generate:
  prefer_subtitles: true          # prefer English subtitle streams
  prefer_audio_language: "auto"   # "en" | "ja" | "auto"
  use_llm_polish: true            # apply LLM to MT outputs
```

Run:
```powershell
python main.py video.mkv --mode generate
```

Output: `outbox/video.en.srt`

Metadata (log): strategy, candidate id, segment count, candidate score.

### Candidate Scoring

After generation, each selected candidate is scored on a **0–100 scale** with
an explainable factor breakdown logged to the console and included in the
returned metadata under the `candidate_score` key.

**Scoring factors:**

| Factor | Max pts | Description |
|--------|---------|-------------|
| `strategy_base` | 70 | Source-type quality. Direct English subtitles score highest; each additional lossy step (ASR, MT) reduces the base score. |
| `qc_pass_rate` | 20 | Fraction of cues free of QC errors. Full 20 pts when all cues pass; proportionally reduced per error violation. |
| `segment_yield` | 10 | Rewards a viable segment count. Full 10 pts at ≥ 5 segments; scales linearly below. |

**Grade thresholds:**

| Grade | Score range |
|-------|-------------|
| A | 80 – 100 |
| B | 60 – 79 |
| C | 40 – 59 |
| D | 20 – 39 |
| F | 0 – 19 |

The `candidate_score` dict in the metadata looks like:

```json
{
  "total_score": 88.0,
  "grade": "A",
  "factors": [
    {
      "name": "strategy_base",
      "description": "Source type quality — direct English sources score highest ...",
      "raw_value": "embedded_en",
      "max_contribution": 70,
      "contribution": 70
    },
    {
      "name": "qc_pass_rate",
      "description": "Fraction of cues free of QC errors ...",
      "raw_value": 1.0,
      "max_contribution": 20,
      "contribution": 20.0
    },
    {
      "name": "segment_yield",
      "description": "Candidate has a viable segment count (full score at ≥ 5 segments)",
      "raw_value": 2,
      "max_contribution": 10,
      "contribution": 4.0
    }
  ]
}
```

## Benchmark Mode

Generates candidates from all enabled sources (see benchmark.sources in config) and computes metrics:
- WER (jiwer)
- BLEU (sacrebleu)
- chrF (sacrebleu)

Config excerpt:
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
```

Run:
```powershell
python main.py video.mkv --mode benchmark
```

Output: `outbox/benchmark_results.json`

## Legacy Subtitle Mode

Original JP→EN pipeline retained for reproducibility:
```powershell
python main.py video.mkv --mode subtitle
```

## Example Workflows

Batch generation:
```powershell
Get-ChildItem inbox/*.mkv | ForEach-Object { python main.py $_.FullName --mode generate }
```

Benchmark then choose best manually:
```powershell
python main.py movie.mkv --mode benchmark
# Inspect benchmark_results.json and select candidate for release
```

## Tracing

Enable OpenTelemetry tracing:
```powershell
$env:TRACING_ENABLED = "1"
python main.py video.mkv --mode generate
```

## Strategy Override Examples

Force audio-first:
```yaml
generate:
  prefer_subtitles: false
  prefer_audio_language: "en"
```

Prefer Japanese audio even if EN audio present:
```yaml
generate:
  prefer_subtitles: false
  prefer_audio_language: "ja"
```

Disable LLM polish (faster):
```yaml
generate:
  use_llm_polish: false
```

## Output Artifacts Summary

| File | Description |
|------|-------------|
| outbox/video.en.srt | Final production subtitles |
| outbox/video.en.qc.json | QC summary (errors, warnings, per-cue violations) |
| outbox/benchmark_results.json | Benchmark comparison metrics & diffs |
| logs/video.json | Candidate chain (legacy pipeline) |

## Error Handling

- Missing ffmpeg: install and ensure on PATH.
- No usable source: ensure at least one audio or subtitle track in JP/EN.
- LLM timeouts: disable polish via `--no-llm` or `generate.use_llm_polish: false`.

## Extensibility Notes

- Add new sources by extending orchestrator.run_generate decision tree.
- Implement new metrics by updating compare_core.compute_metrics.
- Provide HTML reporting for benchmarks (planned).
