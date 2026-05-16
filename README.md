# Anime Subtitle Pipeline

[![CI](https://github.com/beckmt4/anime-subtitle-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/beckmt4/anime-subtitle-pipeline/actions/workflows/ci.yml)

A **production-quality**, **local-only** pipeline for generating English subtitles from Japanese anime, movies, and TV shows. No cloud services or external APIs required.

## Features

- 🎬 **Generation & Evaluation**: Production generate mode (best EN subtitles) + benchmark mode (compare all candidate sources)
- 🎬 **Complete Pipeline**: Video → Audio → Japanese ASR → English Translation → LLM Polishing → SRT Subtitles
- 🚀 **State-of-the-Art Models**:
  - Whisper Large V3 Turbo for Japanese ASR
  - Helsinki-NLP MarianMT for translation
  - Qwen2.5 LLM for natural subtitle polishing
- 🎮 **GPU Optimized**: Automatic CUDA detection with configurable quantization
- ⚙️ **Flexible Configuration**: YAML-based config with dev/prod profiles
- 📝 **Production Ready**: Proper SRT formatting, timing constraints, logging
- 🔒 **100% Local**: No data leaves your machine

## Hardware Requirements

### Development Box (Minimum)

- GPU: NVIDIA RTX A3000 6 GB (or equivalent)
- RAM: 16 GB
- Storage: 20 GB free (for models)

### Production Box (Recommended)

- GPU: NVIDIA RTX 4090 24 GB (or equivalent)
- RAM: 32 GB
- Storage: 30 GB free

**CPU-only mode is supported** but significantly slower.

## Installation

### 1. Prerequisites

#### ffmpeg (Required)

```bash
# Fedora/RHEL:
sudo dnf install ffmpeg

# Debian/Ubuntu:
sudo dnf install ffmpeg

# macOS:
brew install ffmpeg
```

Verify installation:

```bash
ffmpeg -version
```

#### CUDA (For GPU Support)

Download and install NVIDIA CUDA Toolkit:

- CUDA 11.8: <https://developer.nvidia.com/cuda-11-8-0-download-archive>
- CUDA 12.1: <https://developer.nvidia.com/cuda-12-1-0-download-archive>

### 2. Python Environment

Python 3.9+ required.

```bash
# Create virtual environment
python3 -m venv venv

# Activate
source venv/bin/activate
```

### 3. Install Dependencies

#### For CPU-only

```bash
pip install torch
pip install -r requirements.txt
```

#### For GPU (CUDA 12.8 — latest stable)

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

#### For GPU (CUDA 12.1)

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

### Tracing (Optional)

You can enable OpenTelemetry tracing to visualize each pipeline step.

```bash
# Enable tracing with console exporter
TRACING_ENABLED=1 TRACING_EXPORTER=console python main.py video.mkv

# Or send traces to an OTLP endpoint (e.g., Jaeger)
TRACING_ENABLED=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 python main.py video.mkv
```

To run Jaeger locally via Docker (optional):

```bash
docker run --name jaeger -e COLLECTOR_OTLP_ENABLED=true -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.54
# Open Jaeger UI at http://localhost:16686
```

### 4. Ollama Setup (Optional, for LLM Polishing)

Download and install Ollama from https://ollama.ai/

```bash
# Pull the Qwen 2.5 model (7B for dev, 14B for prod)
ollama pull qwen2.5:7b

# For prod box with 24GB GPU:
ollama pull qwen2.5:14b-instruct

# Start Ollama server
ollama serve
```

The server runs on `http://localhost:11434` by default.

For Docker, Unraid, or another machine running Ollama on your LAN, override the
configured endpoint without editing `config.yaml`:

```bash
LLM_BASE_URL=http://192.168.1.147:11434 python main.py video.mkv
```

## Quick Start

### Basic Usage (Generate Mode)

```bash
# Process a video with default settings
python main.py video.mkv
```

This will auto-select the best available path to high-quality English subtitles using the orchestrator logic:

Decision order (default):
1. Embedded English subtitles (demux)
2. English audio → ASR
3. Japanese subtitles → MT (→ LLM)
4. Japanese audio → ASR → MT (→ LLM)

Output: `outbox/video.en.srt`

Override selection via `generate` section in `config.yaml`.

### Benchmark Mode

Generate all possible English subtitle candidates and compare with WER, BLEU, chrF:

```bash
python main.py video.mkv --mode benchmark
```

Benchmark output: `outbox/benchmark_results.json` containing reference candidate, all other candidates, comparisons (metrics + diffs).

Enable pairwise matrix in `config.yaml`:
```yaml
benchmark:
  compare_all_pairs: true
```

### Configuration

Edit `config.yaml` to customize settings:

```yaml
runtime:
  profile: "dev"  # or "prod"

# Dev profile uses:
# - Whisper: int8_float16 quantization
# - Qwen: 7B model
# - Batch size: 8

# Prod profile uses:
# - Whisper: float16 (full precision)
# - Qwen: 14B model
# - Batch size: 16
```

### CLI Options
# Generate (strategy selection)
python main.py video.mkv --mode generate

# Inspect planned generate strategy without running models or writing outputs
python main.py video.mkv --mode generate --inspect-only

# Legacy subtitle pipeline (JP audio → ASR → MT → LLM)
python main.py video.mkv --mode subtitle

# Benchmark all sources
python main.py video.mkv --mode benchmark


```bash
# Use prod profile (for 4090 GPU)
python main.py video.mkv --profile prod

# Skip LLM polishing (faster, uses raw MT)
python main.py video.mkv --no-llm

# Generate SRT only (don't mux into video)
python main.py video.mkv --no-mux

# Use specific audio track
python main.py video.mkv --audio-track 1

# Enable debug logging
python main.py video.mkv --log-level DEBUG
```

## Configuration Guide

### config.yaml Structure (Key Sections)

```yaml
runtime:
  profile: "dev"  # or "prod"

paths:
  inbox: "./inbox"      # Input videos
  outbox: "./outbox"    # Output SRT/videos
  logs: "./logs"        # JSON logs
  temp: "./temp"        # Temporary files

asr:
  model_name: "large-v3-turbo"
  device: "auto"  # auto | cuda | cpu
  
  dev:
    compute_type: "int8_float16"  # Quantized for 6GB GPU
    batch_size: 8
  
  prod:
    compute_type: "float16"       # FP16 for 24GB GPU
    batch_size: 16
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

mt:
  model_name: "Helsinki-NLP/opus-mt-ja-en"
  device: "cpu"
  batch_size: 16

translation:
  engine: "marian"                # marian | llm_direct | hybrid
  fallback_engine: "marian"
  context_window_segments: 4
  mode: "accuracy_first"          # literal | natural_subtitle | accuracy_first
  dialogue_profile: "default"     # default | live_action_adult
  preserve_adult_register: false
  flag_low_confidence: false
  flag_high_risk_content: false
  profiles:
    live_action_adult:
      engine: "llm_direct"
      workflow: "literal_then_natural"
      mode: "accuracy_first"
      context_window_segments: 6
      preserve_adult_register: true
      flag_low_confidence: true
      flag_high_risk_content: true

translation_qc:
  warn_min_ratio: 0.45
  fail_min_ratio: 0.25
  warn_max_ratio: 1.8
  fail_max_ratio: 2.8
  warn_missing_keywords: 1
  fail_missing_keywords: 2
  warn_score_below: 0.80
  fail_score_below: 0.55
  llm_judge:
    enabled: false              # optional local LLM semantic judge
    timeout: 30

generate:
  prefer_subtitles: true          # Prefer existing EN subs
  prefer_audio_language: "auto"   # "en" | "ja" | "auto"
  use_llm_polish: true            # Polish MT outputs

benchmark:
  translation_engines: ["marian"] # compare e.g. ["marian", "llm_direct"]
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
## Orchestrator Architecture

`orchestrator.py` provides high-level flows:

- `run_generate(media, cfg)` – Chooses best source path for production subtitles, returns metadata + writes final `.en.srt`.
- `run_benchmark(media, cfg)` – Delegates to generalized benchmark engine, producing comparison JSON.

Source candidate types:
- `sidecar_en_*` – Direct English sidecar subtitle file discovered next to media
- `embedded_en_sX` – Direct English subtitle track
- `bitmap_en_ocr` – English bitmap subtitle track processed via OCR
- `en_audio_asr_aN` – English audio ASR
- `sidecar_jp_mt[_llm]_` – Japanese sidecar subtitle translated (optional LLM)
- `embedded_jp_mt[_llm]_sY` – Japanese subtitle translated (optional LLM)
- `bitmap_jp_ocr_mt[_llm]_` – Japanese bitmap subtitle OCR → MT (optional LLM)
- `ja_audio_asr_mt[_llm]_aM` – Japanese audio → ASR → MT (optional LLM)

ASR-derived candidates carry `asr_quality` metadata with a clean/warn/fail
status, low-confidence segment counts, threshold values, and per-segment
`meta.asr.warnings`. The metadata is preserved through MT and LLM polish so QC
can report `asr_low_confidence` findings for translated lines that started from
weak transcription. QC also includes translation-judge warnings for likely
untranslated output, omissions, added meaning, and softened explicit dialogue
under the `live_action_adult` profile, plus low-confidence (`[LOW_CONFIDENCE]`)
and high-risk (`[REVIEW_HIGH_RISK]`) review flags. ASR warning density also reduces the
candidate score and routes outputs to review at the configured policy threshold.
OCR-derived candidates carry per-segment `meta.ocr_confidence`; low-confidence OCR
density is also surfaced in QC/scoring and can route outputs to review.
SRT writing clamps adjacent cue timings to keep at least `subtitles.min_gap_sec`
between cues.

Translation-faithfulness QC (`translation_qc.run_translation_qc`) returns
`pass|warn|fail`, a normalized score, and per-segment findings with codes such as
`missing_final_line`, `non_english_leakage`, `possible_omission`,
`possible_added_meaning`, `final_literal_entity_drift`, and `register_softened`.
Generate-mode metadata includes this summary for translated outputs, and benchmark
candidate metadata includes `translation_qc` summaries for JP-source candidates.

Japanese-source translation is selected by `translation.engine`. `marian` is the
offline baseline, `llm_direct` sends each source cue plus nearby context to the
local Ollama-compatible LLM endpoint, and `hybrid` runs MarianMT first, then asks
the LLM to translate with the Marian baseline available as context. Candidate
metadata records engine, model, mode, dialogue profile, fallback status, and
baseline details.
When `translation.dialogue_profile` is `live_action_adult`, the
`translation.profiles.live_action_adult` preset is automatically applied.

Benchmark metrics:
- **WER** – Word Error Rate (lower better)
- **BLEU** – Translation quality (higher better)
- **chrF** – Character F-score (higher better)

Decision logic (simplified):
```
if prefer_subtitles and EN subtitles exist:
  use embedded EN
elif prefer_audio_language == 'en' and EN audio exists:
  use EN audio ASR
elif JP subtitles exist:
  JP subs → MT (→ LLM)
elif (prefer_audio_language in ['ja','auto']) and JP audio exists:
  JP audio → ASR → MT (→ LLM)
elif EN audio exists:
  EN audio ASR
else:
  error (no usable source)
```

## Example Commands

```bash
# Production (auto strategy)
python main.py movie.mkv --mode generate

# Force audio-first by disabling subtitle preference
python main.py movie.mkv --mode generate --config custom.yaml  # custom.yaml sets prefer_subtitles: false

# Benchmark comparisons (reference auto-selected)
python main.py movie.mkv --mode benchmark

# Full pairwise benchmark
python main.py movie.mkv --mode benchmark --config pairwise.yaml  # pairwise.yaml sets compare_all_pairs: true

# Legacy JP→EN pipeline for reproducibility
python main.py movie.mkv --mode subtitle --no-llm
```

## Evaluation Outputs

- `outbox/<video>.en.srt` – Final production subtitles.
- `outbox/benchmark_results.json` – Comparison metrics & diffs.
- `logs/<video>.json` – Candidate chain (legacy pipeline) when enabled.

## Next Steps & Extensibility

- Add HTML report renderer for benchmark results.
- Implement metric toggle enforcement (currently always computed).
- Caching intermediate ASR/MT outputs for faster repeated benchmarking.


llm:
  enabled: true
  base_url: "http://localhost:11434"
  style: "natural"  # or "literal"
  
  dev:
    model_name: "qwen2.5:7b"
  prod:
    model_name: "qwen2.5:14b-instruct"

mux:
  enabled: false  # Set true to auto-mux SRT into video
```

### LLM Styles

**Natural Style** (default):
- More localized, conversational English
- Uses contractions, informal language
- Better for entertainment/anime

**Literal Style**:
- Closer to Japanese phrasing
- Preserves honorifics and cultural terms
- Better for educational content

Change in `config.yaml`:
```yaml
llm:
  style: "literal"  # or "natural"
```

## Pipeline Details

### Step-by-Step Process

1. **Audio Extraction** (ffmpeg)
   - Extracts Japanese audio track
   - Converts to 16kHz mono WAV (Whisper's native format)
   - Auto-detects Japanese track or uses track 0

2. **ASR Transcription** (Faster-Whisper)
   - Whisper Large V3 Turbo model
   - Voice Activity Detection (VAD) filters silence
   - Returns Japanese text with timestamps

3. **Machine Translation** (MarianMT)
   - Helsinki-NLP opus-mt-ja-en model
   - Batch processing for efficiency
   - Runs on CPU to save VRAM

4. **LLM Polishing** (Optional)
   - Local Qwen 2.5 model via Ollama
   - Makes subtitles natural and readable
   - Enforces line length and count constraints

5. **SRT Generation**
   - Proper SRT timestamp formatting
   - Splits long segments at punctuation
   - Enforces min/max duration constraints

6. **Video Muxing** (Optional)
   - Adds SRT as subtitle track to video
   - Uses stream copy (no re-encoding)
   - Preserves all original streams

### Output Files

```
outbox/
  video.en.srt          # English subtitles
  pipeline.db           # SQLite artifact registry, unless artifacts.db_path is configured

logs/
  video.json            # Segment data (JA text, EN raw, EN final)

temp/
  video.wav             # Temporary audio (auto-deleted)
```

If muxing enabled:
```
outbox/
  video.en.mkv          # Video with embedded English subs
```

Successful CLI runs print `registry_run_id=<id>` when the run is recorded in the
artifact registry. The registry is created automatically at
`artifacts.db_path`, or at `outbox/pipeline.db` when no explicit path is set.

## Performance Optimization

### Dev Box (6GB GPU)
- Profile: `dev`
- Whisper: `int8_float16` quantization
- Batch size: 8
- Expected: ~2-3x real-time

### Prod Box (24GB GPU)
- Profile: `prod`
- Whisper: `float16` full precision
- Batch size: 16
- Expected: ~5-10x real-time

### CPU-Only
- Whisper on CPU is very slow (0.1-0.5x real-time)
- Consider using smaller model: `medium` or `small`
- MT and LLM can run on CPU efficiently

## Troubleshooting

### PyTorch Version Error (torch.load security)
**Error**: `ValueError: Due to a serious vulnerability issue in torch.load, even with weights_only=True, we now require users to upgrade torch to at least v2.6`

**Solution**: Upgrade PyTorch to 2.6+
```bash
# For CUDA 11.8:
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For CUDA 12.1:
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# For CPU:
pip install --upgrade torch torchvision torchaudio
```

### CUDA Out of Memory
```yaml
# Reduce batch size in config.yaml
asr:
  dev:
    batch_size: 4  # Default: 8
```

### No Japanese Audio Detected
```bash
# Manually specify audio track
python main.py video.mkv --audio-track 1
```

### LLM Connection Failed
```bash
# Verify Ollama is running
ollama list
ollama serve

# Or disable LLM polishing
python main.py video.mkv --no-llm
```

### ffmpeg Not Found
```bash
sudo dnf install ffmpeg
```

## Advanced Usage

### Batch Processing Multiple Files

```bash
# Process all MKV files in inbox/
for f in inbox/*.mkv; do
    python main.py "$f"
done
```

### Custom Config File

```bash
python main.py video.mkv --config custom_config.yaml
```

### Processing Multiple Audio Tracks

```bash
# List audio tracks first
ffprobe -v error -select_streams a -show_entries stream=index,codec_name:stream_tags=language -of json video.mkv

# Process specific track
python main.py video.mkv --audio-track 2
```

## Model Information

### Whisper Large V3 Turbo
- **Size**: ~1.5 GB
- **Languages**: 99+ including Japanese
- **Download**: Auto-downloaded on first run
- **Location**: `~/.cache/huggingface/hub/`

### Helsinki-NLP opus-mt-ja-en
- **Size**: ~300 MB
- **Task**: Japanese → English translation
- **Download**: Auto-downloaded on first run

### Qwen 2.5 (via Ollama)
- **7B Model**: ~4.7 GB (4-bit quantized)
- **14B Model**: ~9 GB (4-bit quantized)
- **Download**: `ollama pull qwen2.5:7b`
- **Location**: `~/.ollama/models/`

## File Structure

```
anime-subtitle-pipeline/
├── config.yaml          # Main configuration
├── main.py              # CLI entry point
├── config.py            # Config loader
├── audio_utils.py       # ffmpeg integration
├── asr.py               # Faster-Whisper ASR
├── mt.py                # MarianMT translation
├── llm_polish.py        # LLM polishing
├── srt_writer.py        # SRT formatting
├── requirements.txt     # Python dependencies
├── README.md            # This file
├── inbox/               # Input videos (auto-created)
├── outbox/              # Output SRT/videos
├── logs/                # JSON segment logs
└── temp/                # Temporary files
```

## System Requirements Summary

| Component | Dev Box (6GB) | Prod Box (24GB) |
|-----------|---------------|-----------------|
| GPU | RTX A3000 6GB | RTX 4090 24GB |
| RAM | 16 GB | 32 GB |
| Storage | 20 GB | 30 GB |
| Whisper | int8_float16 | float16 |
| LLM | Qwen 7B | Qwen 14B |
| Speed | ~2-3x realtime | ~5-10x realtime |

## License

This tool is provided as-is for personal use. Ensure you have the rights to process any media files.

Model licenses:
- Whisper: MIT License (OpenAI)
- MarianMT: Apache 2.0 License (Helsinki-NLP)
- Qwen: Apache 2.0 License (Alibaba)

## Credits

Built with:
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - Whisper inference with CTranslate2
- [Transformers](https://github.com/huggingface/transformers) - Hugging Face Transformers
- [Ollama](https://ollama.ai/) - Local LLM runtime
- [ffmpeg](https://ffmpeg.org/) - Multimedia framework

## Documentation

Comprehensive documentation is available:

- **[API Documentation](docs/API_DOCUMENTATION.md)** - Complete API reference with examples
- **[Contributing Guide](CONTRIBUTING.md)** - Code style, best practices, and contribution guidelines
- **[Security Policy](SECURITY.md)** - Security best practices and vulnerability reporting
- **[Quick Start](docs/QUICKSTART.md)** - Fast setup guide
- **[Project Summary](docs/PROJECT_SUMMARY.md)** - High-level project overview

## Support

For issues or questions:
1. Check the [API Documentation](docs/API_DOCUMENTATION.md) for detailed usage
2. Review the [Troubleshooting](#troubleshooting) section
3. Verify your configuration matches your hardware
4. Check logs in `logs/` directory
5. Run with `--log-level DEBUG` for detailed output
