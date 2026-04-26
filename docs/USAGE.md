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

Metadata (log): strategy, candidate id, segment count.

### Dry-run / Inspect-only

Use `--dry-run` to preview source discovery and the planned generation path
**without running ASR, MT, LLM polish, mux, or writing any output files**:

```powershell
python main.py video.mkv --mode generate --dry-run
```

The inspect result is printed to the log and includes:

- Detected audio and subtitle streams
- Selected (planned) strategy and confidence tier
- Source candidates and rejection reasons (same schema as a real run)
- Expected output artifact paths (final SRT, QC JSON, raw SRT if applicable)
- Quality risk: confidence tier, review likelihood, heuristic fallback flag
- Whether source selection depends on ambiguous or heuristic fallback behavior
- Whether embedded subtitle streams use a codec that may contain formatting tags
- Whether a Whisper language probe would be required to finalise the strategy

The `--audio-track`, `--extract-en-subs`, and `--no-llm` flags are all
honoured in dry-run mode and affect the planning result.

Programmatic access (no CLI):

```python
from orchestrator import run_generate_inspect
from media_inspect import inspect_media
from config import Config

media = inspect_media("video.mkv")
result = run_generate_inspect(media, Config())
# result["inspect_only"] is always True
# result["planned_strategy"], result["quality_risk"], result["artifact_plan"], ...
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
