# How To Run the Anime Subtitle Pipeline

This guide walks you through running the full, local-only pipeline end-to-end on Fedora Linux.

## TL;DR (Quick Start)

```bash
# From the repo root

# 1) Create and activate a venv
python3 -m venv venv
source venv/bin/activate

# 2) Install PyTorch (choose ONE that matches your setup)
# CPU-only (no GPU):
pip install torch

# CUDA 12.8 GPU:
# pip install torch --index-url https://download.pytorch.org/whl/cu128

# 3) Install other requirements
pip install -r requirements.txt

# 4) Make sure ffmpeg is installed and on PATH
ffmpeg -version

# 5) Run the pipeline
python main.py "Your Video.mkv"
```

Outputs go to `outbox/Your Video.en.srt`. A detailed JSON log is written to `logs/Your Video.json`.

---

## Prerequisites

- Python 3.9 or newer (Fedora 43 ships Python 3.14)
- ffmpeg installed and available in PATH

```bash
sudo dnf install ffmpeg
```

- GPU (optional but faster): NVIDIA with CUDA + recent driver

Verify ffmpeg:

```bash
ffmpeg -version
```

## Environment Setup

1) Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

2) Install PyTorch (pick the variant that matches your system)

```bash
# CPU-only
pip install torch

# CUDA 12.8 (latest stable wheel)
pip install torch --index-url https://download.pytorch.org/whl/cu128

# CUDA 12.1
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

3) Install remaining dependencies

```bash
pip install -r requirements.txt
```

## Optional: Ollama for LLM Polishing

The polishing step uses a local LLM via Ollama. If you skip it, pass `--no-llm` when running.

```bash
# Install Ollama from https://ollama.ai/
ollama pull qwen2.5:7b
ollama serve
```

## Configuration Basics

Edit or review `config.yaml`:

- `runtime.profile`: `dev` (default) or `prod`
- `asr`: Whisper model/device, batch sizes (quantized for dev, FP16 for prod)
- `mt`: MarianMT translation device/batch size
- `llm`: Enable/disable, model name, style (`natural` or `literal`)
- `mux`: If enabled, the pipeline will also mux the SRT back into the video

You can override profile on the CLI with `--profile dev|prod`.

## Run the Pipeline

Basic command:

```bash
python main.py "Your Video.mkv"
```

Common options:

```bash
# Use prod profile (e.g., 24GB GPU)
python main.py "video.mkv" --profile prod

# Skip LLM polishing (faster, uses raw MT output)
python main.py "video.mkv" --no-llm

# Generate SRT only (don't mux back into video)
python main.py "video.mkv" --no-mux

# Force a specific audio track index
python main.py "video.mkv" --audio-track 1

# Verbose logging
python main.py "video.mkv" --log-level DEBUG
```

## Tracing (Optional)

You can enable OpenTelemetry traces to see timing and steps.

Console exporter:

```bash
TRACING_ENABLED=1 TRACING_EXPORTER=console python main.py "video.mkv"
```

OTLP (Jaeger) exporter:

```bash
# Start Jaeger (one-time)
docker run --name jaeger -e COLLECTOR_OTLP_ENABLED=true -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.54

# Send traces to Jaeger via OTLP HTTP
TRACING_ENABLED=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 python main.py "video.mkv"

# Open Jaeger UI: http://localhost:16686 (service: anime-subtitle-pipeline)
```

## Verify Results

- Terminal: look for `✓ Processing complete!`
- Exit code: `echo $?` returns `0` on success
- Files:
  - `outbox/<video>.en.srt` — generated subtitles
  - `logs/<video>.json` — per-segment details (timestamps, JA/EN text)
  - If muxing enabled: `outbox/<video>.en.mkv`

Quick checks:

```bash
# List outputs
ls outbox/*.en.srt
ls logs/*.json

# Preview first 30 lines of SRT
head -30 "outbox/Your Video.en.srt"

# Peek first 40 lines of log
head -40 "logs/Your Video.json"
```

## Common Scenarios

CPU-only run:

```bash
pip install torch
pip install -r requirements.txt
python main.py "video.mkv" --no-llm
```

Process a folder:

```bash
for f in inbox/*.mkv; do
    python main.py "$f" --no-llm
done
```

## Troubleshooting

- PyTorch load error requires 2.6+: install the correct PyTorch build as shown above
- CUDA OOM: lower ASR batch size in `config.yaml` (e.g., dev batch_size: 4)
- ffmpeg not found: `sudo dnf install ffmpeg`
- No Japanese audio detected: specify `--audio-track 1` (or appropriate index)
- Paths with spaces/parentheses: always wrap in quotes `"..."`

If you hit a failure, re-run with `--log-level DEBUG` and share the error snippet for diagnosis.
