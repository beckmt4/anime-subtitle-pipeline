# PROJECT SUMMARY: Anime Subtitle Pipeline

## Overview
A complete, production-ready pipeline for generating English subtitles from Japanese media files using local-only AI models.

## Architecture

```
┌─────────────┐
│ Video File  │
│  (MKV/MP4)  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    AUDIO EXTRACTION                         │
│  ffmpeg: Extract Japanese audio → 16kHz mono WAV           │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    ASR (Speech-to-Text)                     │
│  Faster-Whisper (Large V3 Turbo)                           │
│  Japanese audio → Japanese text + timestamps               │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                  MACHINE TRANSLATION                        │
│  Helsinki-NLP opus-mt-ja-en (MarianMT)                     │
│  Japanese text → Raw English text                          │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│               LLM POLISHING (Optional)                      │
│  Qwen 2.5 (7B/14B) via Ollama                              │
│  Raw English → Natural subtitle English                    │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    SRT GENERATION                           │
│  Format timestamps, split long segments, line breaks       │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│              OPTIONAL: VIDEO MUXING                         │
│  ffmpeg: Embed SRT as subtitle track in video              │
└─────────────────────────────────────────────────────────────┘
```

## File Structure

```
anime-subtitle-pipeline/
├── main.py                  # CLI entry point and pipeline orchestration
├── config.py                # Configuration loader with profile support
├── audio_utils.py           # ffmpeg wrapper for audio/video operations
├── asr.py                   # Faster-Whisper ASR implementation
├── mt.py                    # MarianMT translation implementation
├── llm_polish.py            # Ollama LLM client for subtitle polishing
├── srt_writer.py            # SRT formatting and file writing
├── config.yaml              # Main configuration (dev/prod profiles)
├── requirements.txt         # Python dependencies
├── README.md                # Complete documentation
├── QUICKSTART.md            # Quick start guide
├── example_usage.py         # API usage examples
├── test_pipeline.py         # Testing and validation utilities
├── .gitignore               # Git ignore patterns
├── inbox/                   # Input video files (auto-created)
├── outbox/                  # Output SRT and videos (auto-created)
├── logs/                    # JSON segment logs (auto-created)
└── temp/                    # Temporary audio files (auto-created)
```

## Key Components

### 1. Configuration System (`config.py`)
- YAML-based configuration with dev/prod profiles
- Automatic profile-specific settings (quantization, batch sizes)
- Centralized access to all pipeline settings

### 2. Audio Extraction (`audio_utils.py`)
- ffmpeg wrapper for audio extraction and video muxing
- Auto-detection of Japanese audio tracks
- Audio track listing and validation
- Optimized format for Whisper (16kHz mono WAV)

### 3. ASR Module (`asr.py`)
- Faster-Whisper implementation with CTranslate2 backend
- Whisper Large V3 Turbo for high-quality Japanese transcription
- Voice Activity Detection (VAD) to filter silence
- GPU acceleration with automatic CPU fallback
- Configurable quantization (int8 for 6GB GPU, fp16 for 24GB)

### 4. Machine Translation (`mt.py`)
- Helsinki-NLP opus-mt-ja-en (MarianMT)
- Batch processing for efficiency
- CPU-based to conserve GPU memory
- Segment-by-segment translation to avoid truncation

### 5. LLM Polishing (`llm_polish.py`)
- HTTP client for Ollama-compatible API
- Natural vs literal translation styles
- Enforces subtitle formatting constraints
- Retry logic for transient failures
- Optional concurrent processing

### 6. SRT Writer (`srt_writer.py`)
- Proper SRT timestamp formatting (HH:MM:SS,mmm)
- Automatic segment splitting at punctuation
- Line breaking for readability
- Duration constraints (min/max)
- Validation warnings

### 7. Main Pipeline (`main.py`)
- CLI interface with argument parsing
- Complete pipeline orchestration
- JSON logging for all segments
- Optional video muxing
- Comprehensive error handling

## Configuration Profiles

### Dev Profile (6GB GPU - RTX A3000)
```yaml
asr:
  compute_type: "int8_float16"
  batch_size: 8

llm:
  model_name: "qwen2.5:7b"
```

### Prod Profile (24GB GPU - RTX 4090)
```yaml
asr:
  compute_type: "float16"
  batch_size: 16

llm:
  model_name: "qwen2.5:14b-instruct"
```

## Performance Characteristics

| Environment | GPU | Processing Speed | Example (24min episode) |
|-------------|-----|------------------|-------------------------|
| Dev | RTX A3000 6GB | ~2-3x realtime | ~10 min |
| Prod | RTX 4090 24GB | ~5-10x realtime | ~3 min |
| CPU | None | ~0.1-0.5x realtime | ~60+ min |

## Model Information

| Model | Size | Purpose | Auto-download |
|-------|------|---------|---------------|
| Whisper Large V3 Turbo | ~1.5 GB | Japanese ASR | Yes (first run) |
| opus-mt-ja-en | ~300 MB | JA→EN translation | Yes (first run) |
| Qwen 2.5 7B | ~4.7 GB | Subtitle polishing | Manual (ollama pull) |
| Qwen 2.5 14B | ~9 GB | Subtitle polishing | Manual (ollama pull) |

## CLI Usage

### Basic
```bash
python main.py video.mkv
```

### Advanced
```bash
# Use prod profile
python main.py video.mkv --profile prod

# Skip LLM polishing
python main.py video.mkv --no-llm

# Don't mux into video
python main.py video.mkv --no-mux

# Specific audio track
python main.py video.mkv --audio-track 1

# Debug logging
python main.py video.mkv --log-level DEBUG
```

## API Usage

```python
from config import Config, set_config
from audio_utils import extract_audio_with_ffmpeg
from asr import FasterWhisperASR
from mt import MarianTranslator
from llm_polish import polish_english_subtitles_with_llm
from srt_writer import write_srt_file

# Load config
config = Config("config.yaml")
set_config(config)

# Extract audio
extract_audio_with_ffmpeg("video.mkv", "audio.wav")

# Transcribe
asr = FasterWhisperASR(config)
segments = asr.transcribe_audio_to_segments("audio.wav")

# Translate
translator = MarianTranslator(config)
segments = translator.translate_segments_ja_to_en(segments)

# Polish
segments = polish_english_subtitles_with_llm(segments, config)

# Write SRT
write_srt_file(segments, "output.srt", config)
```

## Data Structures

### Segment
Core data structure passed through pipeline:
```python
@dataclass
class Segment:
    start: float           # Start time (seconds)
    end: float             # End time (seconds)
    text_ja: str           # Japanese text (from ASR)
    text_en_raw: str       # Raw English (from MT)
    text_en_final: str     # Polished English (from LLM or = raw)
```

## Output Files

### SRT File (`outbox/video.en.srt`)
Standard SubRip format with English subtitles

### JSON Log (`logs/video.json`)
Complete segment data including all translation stages:
```json
[
  {
    "start": 0.0,
    "end": 2.5,
    "duration": 2.5,
    "text_ja": "こんにちは",
    "text_en_raw": "Hello",
    "text_en_final": "Hello there!"
  }
]
```

### Muxed Video (optional, `outbox/video.en.mkv`)
Original video with embedded English subtitle track

## Dependencies

### Python Packages
- `pyyaml` - Configuration
- `faster-whisper` - ASR
- `transformers` - MT models
- `torch` - Deep learning backend
- `requests` - HTTP client for LLM
- `sentencepiece`, `protobuf` - Tokenization

### External Tools
- `ffmpeg` - Audio/video processing
- `ollama` - Local LLM runtime (optional)

## Testing

```bash
# Run all tests
python test_pipeline.py

# Test with a video file
python test_pipeline.py path/to/video.mkv
```

## Design Decisions

1. **Faster-Whisper over OpenAI Whisper**: 4-5x faster with CTranslate2 backend
2. **MarianMT on CPU**: Conserves GPU memory for ASR, CPU is fast enough
3. **Segment-by-segment translation**: Avoids truncation issues with long text
4. **Optional LLM polishing**: Balances quality vs speed, can be disabled
5. **SRT format**: Universal subtitle format, easy to edit/validate
6. **YAML configuration**: Human-readable, supports comments, easy to diff
7. **Profile system**: Single config file for multiple hardware configurations
8. **Lazy model loading**: Models load on first use, can be unloaded to free memory
9. **JSON logging**: Complete audit trail of all transformations
10. **Local-only**: No data leaves machine, no API costs, no internet required

## Extensibility

### Adding New Translation Styles
Edit `config.yaml` → `llm.prompts` section

### Changing Models
Edit `config.yaml` → model_name fields

### Custom Processing
Use API (see `example_usage.py`) for programmatic control

### Batch Processing
Use `BatchASR`, `BatchTranslator`, `BatchPolisher` classes

### Alternative LLM Endpoints
Change `llm.base_url` in config (any Ollama-compatible API)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| CUDA OOM | Reduce batch_size or use int8 quantization |
| No Japanese audio | Specify --audio-track or check with ffprobe |
| LLM timeout | Increase llm.timeout or use --no-llm |
| Slow on CPU | Use smaller Whisper model or add GPU |
| ffmpeg not found | Install and add to PATH |

## Future Enhancements

Potential additions (not implemented):
- Web UI for easier operation
- GPU monitoring and dynamic batch sizing
- Multiple subtitle language outputs
- Subtitle timing fine-tuning
- Speaker diarization
- Named entity preservation
- Custom terminology dictionaries
- Batch video processing with queue
- Docker containerization
- API server mode

## License & Credits

- **Whisper**: MIT License (OpenAI)
- **MarianMT**: Apache 2.0 (Helsinki-NLP)
- **Qwen**: Apache 2.0 (Alibaba)
- **Pipeline Code**: Provided as-is for personal use

## Version

v1.0 - Initial production release
- Complete pipeline implementation
- Dev/prod profile support
- Comprehensive documentation
- Testing utilities
- Example scripts
