# Anime Subtitle Pipeline

A **production-quality**, **local-only** pipeline for generating English subtitles from Japanese anime, movies, and TV shows. No cloud services or external APIs required.

## Features

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
```powershell
# Windows: Download from https://ffmpeg.org/ and add to PATH
# Or use Chocolatey:
choco install ffmpeg

# Linux:
sudo apt-get install ffmpeg

# macOS:
brew install ffmpeg
```

Verify installation:
```powershell
ffmpeg -version
```

#### CUDA (For GPU Support)
Download and install NVIDIA CUDA Toolkit:
- CUDA 11.8: https://developer.nvidia.com/cuda-11-8-0-download-archive
- CUDA 12.1: https://developer.nvidia.com/cuda-12-1-0-download-archive

### 2. Python Environment

Python 3.9+ required.

```powershell
# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (Linux/macOS)
source venv/bin/activate
```

### 3. Install Dependencies

#### For GPU (CUDA 11.8):
```powershell
# Install PyTorch 2.6+ with CUDA support (required for security fixes)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install other dependencies
pip install -r requirements.txt
```

#### For GPU (CUDA 12.1):
```powershell
# Install PyTorch 2.6+ with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

#### For CPU-only:
```powershell
pip install -r requirements.txt
```

### Tracing (Optional)

You can enable OpenTelemetry tracing to visualize each pipeline step.

```powershell
# Enable tracing with console exporter
$env:TRACING_ENABLED = "1"
$env:TRACING_EXPORTER = "console"

# Or send traces to an OTLP endpoint (e.g., Jaeger via OpenTelemetry Collector)
$env:TRACING_ENABLED = "1"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"

# Run the pipeline
python main.py video.mkv
```

To run Jaeger locally via Docker (optional):

```powershell
docker run --name jaeger -e COLLECTOR_OTLP_ENABLED=true -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.54
# Open Jaeger UI at http://localhost:16686
```

### 4. Ollama Setup (Optional, for LLM Polishing)

Download and install Ollama from https://ollama.ai/

```powershell
# Pull the Qwen 2.5 model (7B for dev, 14B for prod)
ollama pull qwen2.5:7b

# For prod box with 24GB GPU:
ollama pull qwen2.5:14b-instruct

# Start Ollama server
ollama serve
```

The server runs on `http://localhost:11434` by default.

## Quick Start

### Basic Usage

```powershell
# Process a video with default settings
python main.py video.mkv
```

This will:
1. Extract Japanese audio
2. Transcribe to Japanese text (Whisper)
3. Translate to English (MarianMT)
4. Polish with LLM (if enabled)
5. Generate `video.en.srt` in `outbox/`

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

```powershell
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

### config.yaml Structure

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

mt:
  model_name: "Helsinki-NLP/opus-mt-ja-en"
  device: "cpu"
  batch_size: 16

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
```powershell
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
```powershell
# Manually specify audio track
python main.py video.mkv --audio-track 1
```

### LLM Connection Failed
```powershell
# Verify Ollama is running
ollama list
ollama serve

# Or disable LLM polishing
python main.py video.mkv --no-llm
```

### ffmpeg Not Found
```powershell
# Windows: Add ffmpeg to PATH
$env:PATH += ";C:\path\to\ffmpeg\bin"

# Or install via Chocolatey
choco install ffmpeg
```

## Advanced Usage

### Batch Processing Multiple Files

```powershell
# Process all MKV files in inbox/
Get-ChildItem inbox/*.mkv | ForEach-Object {
    python main.py $_.FullName
}
```

### Custom Config File

```powershell
python main.py video.mkv --config custom_config.yaml
```

### Processing Multiple Audio Tracks

```powershell
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

- **[API Documentation](API_DOCUMENTATION.md)** - Complete API reference with examples
- **[Contributing Guide](CONTRIBUTING.md)** - Code style, best practices, and contribution guidelines
- **[Security Policy](SECURITY.md)** - Security best practices and vulnerability reporting
- **[Quick Start](QUICKSTART.md)** - Fast setup guide
- **[Project Summary](PROJECT_SUMMARY.md)** - High-level project overview

## Support

For issues or questions:
1. Check the [API Documentation](API_DOCUMENTATION.md) for detailed usage
2. Review the [Troubleshooting](#troubleshooting) section
3. Verify your configuration matches your hardware
4. Check logs in `logs/` directory
5. Run with `--log-level DEBUG` for detailed output
