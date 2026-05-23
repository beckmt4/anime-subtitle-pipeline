# Quick Reference Guide

## Common Commands

### Basic Usage

```bash
# Process single video
python main.py video.mkv

# Use production profile
python main.py video.mkv --profile prod

# Skip LLM polishing (faster)
python main.py video.mkv --no-llm

# Generate SRT only (no muxing)
python main.py video.mkv --no-mux

# Specify audio track
python main.py video.mkv --audio-track 1

# Debug mode
python main.py video.mkv --log-level DEBUG
```

### Batch Processing

```bash
# Process all videos in inbox/
python batch_process.py

# Process specific files
python batch_process.py video1.mkv video2.mkv video3.mkv

# Watch inbox/ for new files
python batch_process.py --watch

# Skip existing files
python batch_process.py --skip-existing
```

### Configuration

```bash
# Use custom config
python main.py video.mkv --config custom_config.yaml

# Override profile
python main.py video.mkv --profile prod
```

---

## Configuration Quick Reference

### config.yaml Structure

```yaml
runtime:
  profile: "dev"  # or "prod"

paths:
  inbox: "./inbox"
  outbox: "./outbox"
  logs: "./logs"
  temp: "./temp"

asr:
  model_name: "large-v3-turbo"
  device: "auto"  # auto | cuda | cpu
  dev:
    compute_type: "int8_float16"
    batch_size: 8
  prod:
    compute_type: "float16"
    batch_size: 16

mt:
  model_name: "Helsinki-NLP/opus-mt-ja-en"
  device: "cpu"
  batch_size: 16

llm:
  enabled: true
  base_url: "http://localhost:11434"
  dev:
    model_name: "qwen2.5:7b"
  prod:
    model_name: "qwen2.5:14b-instruct"
  style: "natural"  # or "literal"

mux:
  enabled: false  # Set true to auto-mux
```

### Profile Comparison

| Setting | Dev (6GB GPU) | Prod (24GB GPU) |
|---------|---------------|-----------------|
| Compute Type | int8_float16 | float16 |
| Batch Size | 8 | 16 |
| LLM Model | qwen2.5:7b | qwen2.5:14b-instruct |
| Speed | ~2-3x realtime | ~5-10x realtime |
| VRAM Usage | ~4-5 GB | ~8-10 GB |

---

## File Locations

### Input/Output

```
project/
├── inbox/          # Place videos here
├── outbox/         # SRT files appear here
│   └── video.en.srt
├── logs/           # JSON segment logs
│   └── video.json
└── temp/           # Temporary audio (auto-deleted)
    └── video.wav
```

### Configuration

```
project/
├── config.yaml     # Main configuration
└── .gitignore      # Git ignore rules
```

### Documentation

```
project/
├── README.md                   # Main documentation
├── API_DOCUMENTATION.md        # API reference
├── CONTRIBUTING.md             # Contribution guide
├── SECURITY.md                 # Security policy
├── CHANGELOG.md                # Version history
├── QUICK_REFERENCE.md          # This file
└── CODE_REVIEW_SUMMARY.md      # Code review results
```

---

## Troubleshooting Quick Fixes

### ffmpeg Not Found

```bash
# Windows (PowerShell)
choco install ffmpeg

# Or add to PATH
$env:PATH += ";C:\path\to\ffmpeg\bin"

# Verify
ffmpeg -version
```

### CUDA Out of Memory

```yaml
# Edit config.yaml
asr:
  dev:
    batch_size: 4  # Reduce from 8
```

### LLM Connection Failed

```bash
# Check Ollama is running
ollama list
ollama serve

# Or disable LLM
python main.py video.mkv --no-llm
```

### PyTorch Version Error

```bash
# Upgrade PyTorch to 2.6+
pip install --upgrade torch>=2.6.0

# For CUDA 11.8
pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu118

# For CUDA 12.1
pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu121
```

### No Japanese Audio Detected

```bash
# List audio tracks
ffprobe -v error -select_streams a -show_entries stream=index:stream_tags=language video.mkv

# Specify track manually
python main.py video.mkv --audio-track 1
```

---

## Environment Variables

### Tracing

```powershell
# Enable console tracing
$env:TRACING_ENABLED = "1"
$env:TRACING_EXPORTER = "console"

# Enable OTLP tracing (Jaeger)
$env:TRACING_ENABLED = "1"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
```

### Configuration

```powershell
# Override config path
$env:CONFIG_PATH = "custom_config.yaml"

# Override profile
$env:PROFILE = "prod"
```

---

## API Quick Reference

### Process Single Video

```python
from config import Config, set_config
from main import process_video

config = Config("config.yaml")
set_config(config)

result = process_video(
    video_path="video.mkv",
    config=config,
    no_llm=False,
    no_mux=False
)

print(f"Success: {result['success']}")
print(f"SRT: {result['srt_file']}")
```

### Extract Audio

```python
from audio_utils import extract_audio_with_ffmpeg

audio_path = extract_audio_with_ffmpeg(
    input_video_path="video.mkv",
    output_audio_path="temp/audio.wav",
    audio_track_index=0
)
```

### Transcribe Audio

```python
from config import Config
from asr import FasterWhisperASR

config = Config()
asr = FasterWhisperASR(config)

segments, _candidate = asr.transcribe_audio_to_segments("audio.wav")
for seg in segments:
    print(f"{seg.start:.2f}s: {seg.text}")

asr.unload_model()
```

### Translate Segments

```python
from config import Config
from mt import translate_candidate_jp_to_en

config = Config()
mt_candidate = translate_candidate_jp_to_en(_candidate, config)
for seg in mt_candidate.segments:
    print(seg.text)
```

### Polish with LLM

```python
from config import Config
from llm_polish import polish_candidate_with_llm

config = Config()
final_candidate = polish_candidate_with_llm(mt_candidate, config)
for seg in final_candidate.segments:
    print(seg.text)
```

### Write SRT

```python
from config import Config
from srt_writer import write_candidate_srt

config = Config()
srt_path = write_candidate_srt(final_candidate, "output.srt", config)
print(f"SRT written to: {srt_path}")
```

---

## Performance Tips

### Speed Optimization

1. **Use GPU** for ASR (10-20x faster)
2. **Skip LLM** for faster processing: `--no-llm`
3. **Use prod profile** on high-end hardware: `--profile prod`
4. **Increase batch size** if you have VRAM

### Memory Optimization

1. **Reduce batch size** in config.yaml
2. **Use int8_float16** quantization (dev profile)
3. **Unload models** between files
4. **Clear CUDA cache** periodically

### Quality Optimization

1. **Enable LLM polishing** for better subtitles
2. **Use prod profile** for better accuracy
3. **Adjust LLM temperature** (lower = more consistent)
4. **Use literal style** for educational content

---

## Model Information

### Whisper Large V3 Turbo

- **Size:** ~1.5 GB
- **Languages:** 99+ including Japanese
- **Download:** Auto on first run
- **Location:** `~/.cache/huggingface/hub/`

### Helsinki-NLP opus-mt-ja-en

- **Size:** ~300 MB
- **Task:** Japanese → English
- **Download:** Auto on first run
- **Location:** `~/.cache/huggingface/hub/`

### Qwen 2.5

- **7B Model:** ~4.7 GB (4-bit quantized)
- **14B Model:** ~9 GB (4-bit quantized)
- **Download:** `ollama pull qwen2.5:7b`
- **Location:** `~/.ollama/models/`

---

## Keyboard Shortcuts

### During Processing

- `Ctrl+C` - Stop processing (graceful shutdown)
- `Ctrl+Z` - Suspend (Unix/Linux only)

### In Watch Mode

- `Ctrl+C` - Stop watching

---

## Log Levels

```bash
# Minimal output
python main.py video.mkv --log-level ERROR

# Normal output (default)
python main.py video.mkv --log-level INFO

# Detailed output
python main.py video.mkv --log-level DEBUG

# Everything
python main.py video.mkv --log-level DEBUG
```

### Log Output

```
INFO - Processing: video.mkv
INFO - [1/6] Extracting audio track...
INFO - [2/6] Running Japanese ASR...
INFO - Transcribed 150 Japanese segments
INFO - [3/6] Translating Japanese to English...
INFO - Translation complete
INFO - [4/6] Polishing subtitles with LLM...
INFO - Polishing complete
INFO - [5/6] Writing SRT subtitle file...
INFO - ✓ SRT file created: video.en.srt
INFO - [6/6] Skipping video muxing (disabled)
INFO - ✓ Processing complete!
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 130 | Interrupted by user (Ctrl+C) |

---

## Useful ffmpeg Commands

### List Audio Tracks

```bash
ffprobe -v error -select_streams a -show_entries stream=index,codec_name:stream_tags=language -of json video.mkv
```

### List Subtitle Tracks

```bash
ffprobe -v error -select_streams s -show_entries stream=index,codec_name:stream_tags=language -of json video.mkv
```

### Extract Subtitle

```bash
ffmpeg -i video.mkv -map 0:s:0 output.srt
```

### Mux Subtitle

```bash
ffmpeg -i video.mkv -i subtitle.srt -c copy -c:s srt output.mkv
```

---

## Ollama Commands

### List Models

```bash
ollama list
```

### Pull Model

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b-instruct
```

### Remove Model

```bash
ollama rm qwen2.5:7b
```

### Start Server

```bash
ollama serve
```

### Test Model

```bash
ollama run qwen2.5:7b "Hello, how are you?"
```

---

## Git Commands

### Clone Repository

```bash
git clone https://github.com/yourusername/anime-subtitle-pipeline.git
cd anime-subtitle-pipeline
```

### Update Repository

```bash
git pull origin main
```

### Check Status

```bash
git status
```

---

## Python Virtual Environment

### Create Environment

```bash
python -m venv venv
```

### Activate

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Windows CMD
venv\Scripts\activate.bat

# Linux/macOS
source venv/bin/activate
```

### Deactivate

```bash
deactivate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Update Dependencies

```bash
pip install --upgrade -r requirements.txt
```

---

## System Requirements

### Minimum

- **OS:** Windows 10, Ubuntu 20.04, macOS 11+
- **Python:** 3.9+
- **GPU:** NVIDIA RTX A3000 6GB (or CPU-only)
- **RAM:** 16 GB
- **Storage:** 20 GB

### Recommended

- **OS:** Windows 11, Ubuntu 22.04, macOS 12+
- **Python:** 3.10+
- **GPU:** NVIDIA RTX 4090 24GB
- **RAM:** 32 GB
- **Storage:** 30 GB

---

## Support Resources

### Documentation

- [README.md](README.md) - Main documentation
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - API reference
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guide
- [SECURITY.md](SECURITY.md) - Security policy

### External Resources

- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper)
- [Transformers](https://huggingface.co/docs/transformers)
- [Ollama](https://ollama.ai/)
- [ffmpeg](https://ffmpeg.org/documentation.html)

---

## Quick Checklist

### Before First Run

- [ ] Python 3.9+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] PyTorch 2.6+ installed
- [ ] ffmpeg installed and in PATH
- [ ] Ollama installed (optional)
- [ ] Qwen model pulled (optional)
- [ ] config.yaml configured
- [ ] GPU drivers updated (if using GPU)

### Before Processing

- [ ] Video file in inbox/ or path specified
- [ ] Sufficient disk space (2x video size)
- [ ] GPU memory available (if using GPU)
- [ ] Ollama server running (if using LLM)

### After Processing

- [ ] Check outbox/ for SRT file
- [ ] Check logs/ for JSON log
- [ ] Verify subtitle quality
- [ ] Clean up temp/ if needed

---

*For detailed information, see the full documentation files.*
