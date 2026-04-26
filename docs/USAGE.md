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

translation:
  engine: "marian"                # marian | llm_direct | hybrid
  fallback_engine: "marian"
  context_window_segments: 4
  mode: "accuracy_first"          # literal | natural_subtitle | accuracy_first
```

Run:
```powershell
python main.py video.mkv --mode generate
```

Output: `outbox/video.en.srt`

Metadata: the CLI prints `registry_run_id=<id>` when the run is recorded in the
artifact registry. The registry defaults to `outbox/pipeline.db` unless
`artifacts.db_path` is configured.

When generate mode uses ASR, candidates include `asr_quality` metadata:
- `status`: `clean`, `warn`, or `fail`
- `low_confidence_segment_count`: number of ASR segments with warning signals
- `warning_count`: total ASR warning signals
- per-segment `meta.asr.warnings`: deterministic findings such as high
  no-speech probability, low average log probability, high compression ratio,
  unusually short/long segments, repeated text, long gaps, or low Japanese
  character ratio

The same ASR metadata is propagated through MT and LLM outputs. QC summaries can
include `asr_low_confidence` warning findings so weak translated lines can be
traced back to uncertain transcription instead of being blamed only on MT.
Generate scoring penalizes ASR warning density, and the routing policy sends
outputs to review when ASR warnings affect at least
`policy.routing.asr_warning_review_density` of cues. The default is 10%.

Japanese-source paths use `translation.engine`:
- `marian`: current MarianMT baseline.
- `llm_direct`: direct local LLM translation with nearby source context.
- `hybrid`: MarianMT baseline plus LLM direct translation with the baseline
  available as context.

If `llm_direct` or `hybrid` fails, the configured fallback engine is used and
candidate metadata records `translation_fallback`, `fallback_engine`, and
`fallback_reason`.

Inspect the planned generate strategy without running ASR, MT, LLM, QC, muxing,
registry writes, or output writes:

```powershell
python main.py video.mkv --mode generate --inspect-only
```

## Benchmark Mode

Generates candidates from all enabled sources (see benchmark.sources in config) and computes metrics:
- WER (jiwer)
- BLEU (sacrebleu)
- chrF (sacrebleu)

Config excerpt:
```yaml
benchmark:
  translation_engines:
    - marian
    # - llm_direct
    # - hybrid
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

When `benchmark.translation_engines` contains multiple engines, each Japanese
subtitle or Japanese ASR source produces one candidate per engine so benchmark
comparisons can measure engine behavior side by side.

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

Use direct LLM translation:
```yaml
translation:
  engine: "llm_direct"
  fallback_engine: "marian"
  mode: "accuracy_first"
  context_window_segments: 4
```

Compare translation engines in benchmark mode:
```yaml
benchmark:
  translation_engines: ["marian", "llm_direct", "hybrid"]
```

Tune ASR warning thresholds:
```yaml
asr:
  quality:
    warn_no_speech_prob_above: 0.60
    warn_avg_logprob_below: -1.00
    warn_compression_ratio_above: 2.40
    warn_min_duration_sec: 0.25
    warn_max_duration_sec: 12.0
    warn_gap_sec: 6.0
    warn_repeated_text_count: 3
    warn_japanese_char_ratio_below: 0.20
    fail_low_confidence_ratio: 0.50
```

Tune ASR warning routing and SRT overlap prevention:
```yaml
policy:
  routing:
    asr_warning_review_density: 0.10

subtitles:
  min_gap_sec: 0.05
```

## Output Artifacts Summary

| File | Description |
|------|-------------|
| outbox/video.en.srt | Final production subtitles |
| outbox/video.en.mkv | Optional muxed video with embedded English subtitles |
| outbox/pipeline.db | SQLite artifact registry, unless `artifacts.db_path` is configured |
| outbox/benchmark_results.json | Benchmark comparison metrics & diffs |
| logs/video.json | Candidate chain (legacy pipeline) |

## Error Handling

- Missing ffmpeg: install and ensure on PATH.
- No usable source: ensure at least one audio or subtitle track in JP/EN.
- LLM timeouts: disable polish via `--no-llm` or `generate.use_llm_polish: false`.
- Remote Ollama endpoint: set `LLM_BASE_URL`, for example `LLM_BASE_URL=http://192.168.1.147:11434`.

## Extensibility Notes

- Add new sources by extending orchestrator.run_generate decision tree.
- Implement new metrics by updating compare_core.compute_metrics.
- Provide HTML reporting for benchmarks (planned).
