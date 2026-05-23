# API Documentation

## Overview

This document provides comprehensive API documentation for the Anime Subtitle Pipeline. It covers all public classes, functions, and their usage patterns.

## Table of Contents

1. [Configuration Management](#configuration-management)
2. [Audio Processing](#audio-processing)
3. [ASR (Speech Recognition)](#asr-speech-recognition)
4. [Machine Translation](#machine-translation)
5. [LLM Polishing](#llm-polishing)
6. [SRT Writing](#srt-writing)
7. [Tracing](#tracing)
8. [Data Structures](#data-structures)

---

## Configuration Management

### Module: `config.py`

#### Class: `Config`

Central configuration manager that loads and validates YAML configuration files.

**Constructor:**
```python
Config(config_path: str = "config.yaml", profile_override: Optional[str] = None)
```

**Parameters:**
- `config_path`: Path to YAML configuration file (default: "config.yaml")
- `profile_override`: Override profile from CLI ("dev" or "prod")

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `profile` | str | Active profile ("dev" or "prod") |
| `asr_model_name` | str | Whisper model name |
| `asr_device` | str | Device for ASR ("cuda", "cpu", or "auto") |
| `asr_compute_type` | str | Quantization type |
| `asr_batch_size` | int | Batch size for ASR |
| `mt_model_name` | str | MarianMT model name |
| `mt_device` | str | Device for MT |
| `llm_enabled` | bool | Whether LLM polishing is enabled |
| `llm_model_name` | str | LLM model name |
| `llm_base_url` | str | LLM API endpoint |

**Methods:**

```python
def get(self, *keys: str, default: Any = None) -> Any
```
Get configuration value using dot notation.

```python
def get_path(self, path_name: str) -> str
```
Get absolute path from paths section.

```python
def get_llm_prompt(self, style: Optional[str] = None) -> str
```
Get LLM system prompt for specified style.

**Example:**
```python
from config import Config, set_config

# Load configuration
config = Config("config.yaml", profile_override="prod")
set_config(config)

# Access settings
print(config.asr_model_name)  # "large-v3-turbo"
print(config.asr_device)      # "cuda" or "cpu"
```

---

## Audio Processing

### Module: `audio_utils.py`

#### Function: `check_ffmpeg_available()`

```python
def check_ffmpeg_available() -> bool
```

Check if ffmpeg is available on the system.

**Returns:** `True` if ffmpeg is accessible, `False` otherwise

**Example:**
```python
from audio_utils import check_ffmpeg_available

if not check_ffmpeg_available():
    print("Error: ffmpeg not found")
    exit(1)
```

#### Function: `extract_audio_with_ffmpeg()`

```python
def extract_audio_with_ffmpeg(
    input_video_path: str,
    output_audio_path: str,
    audio_track_index: int = 0,
    target_sample_rate: int = 16000,
    target_channels: int = 1
) -> Path
```

Extract audio track from video file to WAV format optimized for Whisper.

**Parameters:**
- `input_video_path`: Path to input video
- `output_audio_path`: Path for output WAV file
- `audio_track_index`: Audio track index (default: 0)
- `target_sample_rate`: Sample rate in Hz (default: 16000)
- `target_channels`: Number of channels (default: 1 for mono)

**Returns:** Path to extracted audio file

**Raises:**
- `FileNotFoundError`: If input video doesn't exist
- `RuntimeError`: If ffmpeg extraction fails

**Example:**
```python
from audio_utils import extract_audio_with_ffmpeg

audio_path = extract_audio_with_ffmpeg(
    input_video_path="video.mkv",
    output_audio_path="temp/audio.wav",
    audio_track_index=0
)
```

#### Function: `find_japanese_audio_track()`

```python
def find_japanese_audio_track(video_path: str) -> Optional[int]
```

Automatically detect Japanese audio track.

**Parameters:**
- `video_path`: Path to video file

**Returns:** Index of Japanese track, or `None` if not found

**Example:**
```python
from audio_utils import find_japanese_audio_track

track_index = find_japanese_audio_track("video.mkv")
if track_index is None:
    track_index = 0  # Default to first track
```

#### Function: `mux_subtitle_to_video()`

```python
def mux_subtitle_to_video(
    input_video_path: str,
    subtitle_path: str,
    output_video_path: str,
    subtitle_language: str = "eng",
    subtitle_title: str = "English"
) -> Path
```

Mux SRT subtitle file into video without re-encoding.

**Parameters:**
- `input_video_path`: Original video file
- `subtitle_path`: SRT subtitle file
- `output_video_path`: Output video path
- `subtitle_language`: ISO 639-2 language code (default: "eng")
- `subtitle_title`: Subtitle track title (default: "English")

**Returns:** Path to output video

**Example:**
```python
from audio_utils import mux_subtitle_to_video

output = mux_subtitle_to_video(
    input_video_path="video.mkv",
    subtitle_path="video.en.srt",
    output_video_path="video.en.mkv"
)
```

---

## ASR (Speech Recognition)

### Module: `asr.py`

#### Class: `Segment`

Data structure representing a transcribed audio segment.

**Attributes:**
- `start` (float): Start time in seconds
- `end` (float): End time in seconds
- `text_ja` (str): Japanese transcription
- `text_en_raw` (str): Raw English translation (added by MT)
- `text_en_final` (str): Polished English (added by LLM)

**Properties:**
- `duration` (float): Segment duration in seconds

**Example:**
```python
from asr import Segment

seg = Segment(
    start=10.5,
    end=15.2,
    text_ja="こんにちは"
)
print(seg.duration)  # 4.7
```

#### Class: `FasterWhisperASR`

Japanese ASR using Faster-Whisper.

**Constructor:**
```python
FasterWhisperASR(config: Config)
```

**Methods:**

```python
def load_model(self) -> None
```
Load the Whisper model. Downloads on first run.

```python
def transcribe_audio_to_segments(
    self,
    audio_path: str,
    language: Optional[str] = None
) -> List[Segment]
```
Transcribe audio file to Japanese text segments.

**Parameters:**
- `audio_path`: Path to audio file (WAV recommended)
- `language`: Language code (default: from config, typically "ja")

**Returns:** List of Segment objects with Japanese transcriptions

**Raises:**
- `FileNotFoundError`: If audio file doesn't exist
- `RuntimeError`: If transcription fails

```python
def unload_model(self) -> None
```
Unload model to free memory.

**Example:**
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

#### Class: `BatchASR`

Context manager for processing multiple files with persistent model.

**Example:**
```python
from config import Config
from asr import BatchASR

config = Config()

with BatchASR(config) as asr:
    for audio_file in audio_files:
        segments = asr.transcribe(audio_file)
        # Process segments...
```

---

## Machine Translation

### Module: `mt.py`

#### Class: `MarianTranslator`

Japanese to English translator using MarianMT.

**Constructor:**
```python
MarianTranslator(config: Config)
```

**Methods:**

```python
def load_model(self) -> None
```
Load MarianMT model and tokenizer.

```python
def translate_text(self, text: str) -> str
```
Translate single Japanese text to English.

**Parameters:**
- `text`: Japanese text

**Returns:** English translation

```python
def translate_batch(self, texts: List[str]) -> List[str]
```
Translate batch of Japanese texts (more efficient).

**Parameters:**
- `texts`: List of Japanese texts

**Returns:** List of English translations

```python
def translate_segments_ja_to_en(self, segments: List[Segment]) -> List[Segment]
```
Translate Japanese text in segments to English.

**Parameters:**
- `segments`: List of Segment objects with `text_ja`

**Returns:** Same segments with `text_en_raw` populated

```python
def unload_model(self) -> None
```
Unload model to free memory.

**Example:**
```python
from config import Config
from mt import MarianTranslator

config = Config()
translator = MarianTranslator(config)

# Single translation
english = translator.translate_text("こんにちは")

# Batch translation
texts = ["こんにちは", "ありがとう"]
translations = translator.translate_batch(texts)

translator.unload_model()
```

---

## LLM Polishing

### Module: `llm_polish.py`

#### Class: `LLMPolisher`

LLM-based subtitle polisher using Ollama-compatible API.

**Constructor:**
```python
LLMPolisher(config: Config)
```

**Methods:**

```python
def check_connection(self) -> bool
```
Check if LLM endpoint is accessible.

**Returns:** `True` if endpoint responds, `False` otherwise

```python
def polish_text(
    self,
    text_ja: str,
    text_en_raw: str,
    style: Optional[str] = None,
    retry_count: int = 2
) -> str
```
Polish single English subtitle using LLM.

**Parameters:**
- `text_ja`: Original Japanese text (for context)
- `text_en_raw`: Raw machine-translated English
- `style`: Override style ("natural" or "literal")
- `retry_count`: Number of retries on failure

**Returns:** Polished English text, or original on failure

```python
def polish_segments(
    self,
    segments: List[Segment],
    style: Optional[str] = None
) -> List[Segment]
```
Polish all segments in list.

**Parameters:**
- `segments`: List of Segment objects with `text_ja` and `text_en_raw`
- `style`: Override style for this batch

**Returns:** Same segments with `text_en_final` populated

**Example:**
```python
from config import Config
from llm_polish import LLMPolisher

config = Config()
polisher = LLMPolisher(config)

if polisher.check_connection():
    segments = polisher.polish_segments(segments)
else:
    print("LLM endpoint not available")
```

#### Function: `polish_english_subtitles_with_llm()`

```python
def polish_english_subtitles_with_llm(
    segments: List[Segment],
    config: Config,
    style: Optional[str] = None
) -> List[Segment]
```

Convenience function for LLM polishing.

**Parameters:**
- `segments`: List of Segment objects
- `config`: Configuration object
- `style`: Override configured style

**Returns:** Segments with polished English in `text_en_final`

---

## SRT Writing

### Module: `srt_writer.py`

#### Function: `format_timestamp_srt()`

```python
def format_timestamp_srt(seconds: float) -> str
```

Format timestamp in SRT format (HH:MM:SS,mmm).

**Parameters:**
- `seconds`: Time in seconds (must be non-negative)

**Returns:** Formatted timestamp string

**Raises:**
- `ValueError`: If seconds is negative

**Example:**
```python
from srt_writer import format_timestamp_srt

timestamp = format_timestamp_srt(90.5)
print(timestamp)  # "00:01:30,500"
```

#### Class: `SRTWriter`

SRT subtitle file writer with formatting constraints.

**Constructor:**
```python
SRTWriter(config: Config)
```

**Methods:**

```python
def prepare_segments(self, segments: List[Segment]) -> List[Segment]
```
Prepare segments by applying timing and splitting constraints.

**Parameters:**
- `segments`: Original segments

**Returns:** Prepared segments ready for writing

```python
def write_srt(self, segments: List[Segment], output_path: str) -> Path
```
Write segments to SRT file.

**Parameters:**
- `segments`: List of Segment objects with `text_en_final`
- `output_path`: Output SRT file path

**Returns:** Path to written file

**Raises:**
- `ValueError`: If segments list is empty

```python
def validate_segments(self, segments: List[Segment]) -> List[str]
```
Validate segments for common issues.

**Parameters:**
- `segments`: Segments to validate

**Returns:** List of warning messages (empty if no issues)

**Example:**
```python
from config import Config
from srt_writer import SRTWriter

config = Config()
writer = SRTWriter(config)

# Validate first
warnings = writer.validate_segments(segments)
if warnings:
    for warning in warnings:
        print(f"Warning: {warning}")

# Write SRT
srt_path = writer.write_srt(segments, "output.srt")
```

#### Function: `write_srt_file()`

```python
def write_srt_file(segments: List[Segment], output_path: str, config: Config) -> Path
```

Convenience function to write SRT file with validation.

**Parameters:**
- `segments`: List of Segment objects
- `output_path`: Output file path
- `config`: Configuration object

**Returns:** Path to written SRT file

---

## Tracing

### Module: `tracing.py`

#### Function: `setup_tracing()`

```python
def setup_tracing(service_name: str = "anime-subtitle-pipeline") -> None
```

Initialize OpenTelemetry tracing if enabled by environment variable.

**Parameters:**
- `service_name`: Service name for traces

**Environment Variables:**
- `TRACING_ENABLED`: Set to "1" to enable tracing
- `TRACING_EXPORTER`: "console" or "otlp" (default: "otlp" if endpoint set)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OTLP endpoint URL (e.g., "http://localhost:4318")

**Example:**
```python
from tracing import setup_tracing

setup_tracing(service_name="my-pipeline")
```

#### Function: `start_span()`

```python
@contextmanager
def start_span(name: str, **attributes)
```

Context manager to start a span and set attributes.

**Parameters:**
- `name`: Span name
- `**attributes`: Key-value pairs to set as span attributes

**Example:**
```python
from tracing import start_span

with start_span("asr_transcription", model="large-v3-turbo", device="cuda"):
    # Transcription code here
    pass
```

---

## Data Structures

### Segment

Core data structure passed through the pipeline.

```python
@dataclass
class Segment:
    start: float           # Start time in seconds
    end: float             # End time in seconds
    text_ja: str           # Japanese transcription
    text_en_raw: str = ""  # Raw English translation
    text_en_final: str = "" # Polished English
    
    @property
    def duration(self) -> float:
        """Duration in seconds"""
        return self.end - self.start
```

**Lifecycle:**
1. Created by ASR with `start`, `end`, `text_ja`
2. MT adds `text_en_raw`
3. LLM adds `text_en_final`
4. SRT writer uses `text_en_final` for output

---

## Error Handling

### Common Exceptions

| Exception | Module | Description |
|-----------|--------|-------------|
| `FileNotFoundError` | All | Input file doesn't exist |
| `RuntimeError` | ASR, MT | Model loading/processing failed |
| `ValueError` | SRT Writer | Invalid input data |
| `subprocess.CalledProcessError` | Audio Utils | ffmpeg command failed |

### Best Practices

1. **Always check file existence** before processing
2. **Use try-except blocks** for external dependencies (ffmpeg, Ollama)
3. **Validate configuration** before starting pipeline
4. **Log errors with context** for debugging

**Example:**
```python
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def safe_process(video_path: str):
    try:
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        
        # Process video...
        
    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        return None
    except RuntimeError as e:
        logger.error(f"Processing error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return None
```

---

## Performance Tips

### Memory Management

1. **Unload models** when not needed:
   ```python
   asr.unload_model()
   translator.unload_model()
   ```

2. **Use batch processing** for multiple files:
   ```python
   with BatchASR(config) as asr:
       for file in files:
           segments = asr.transcribe(file)
   ```

3. **Adjust batch sizes** based on available VRAM:
   ```yaml
   asr:
     dev:
       batch_size: 8   # For 6GB GPU
     prod:
       batch_size: 16  # For 24GB GPU
   ```

### Speed Optimization

1. **Use GPU** for ASR (10-20x faster than CPU)
2. **Skip LLM polishing** for faster processing:
   ```bash
   python main.py video.mkv --no-llm
   ```
3. **Use prod profile** on high-end hardware:
   ```bash
   python main.py video.mkv --profile prod
   ```

---

## Integration Examples

### Complete Pipeline

```python
from pathlib import Path
from config import Config, set_config
from audio_utils import extract_audio_with_ffmpeg, find_japanese_audio_track
from asr import FasterWhisperASR
from mt import MarianTranslator
from llm_polish import polish_english_subtitles_with_llm
from srt_writer import write_srt_file

# Setup
config = Config("config.yaml")
set_config(config)

video_path = "video.mkv"
audio_path = "temp/audio.wav"
srt_path = "output/video.en.srt"

# Extract audio
track = find_japanese_audio_track(video_path) or 0
extract_audio_with_ffmpeg(video_path, audio_path, track)

# Transcribe
asr = FasterWhisperASR(config)
segments = asr.transcribe_audio_to_segments(audio_path)
asr.unload_model()

# Translate
mt_candidate = translate_candidate_jp_to_en(_candidate, config)

# Polish (optional)
if config.llm_enabled:
    final_candidate = polish_candidate_with_llm(mt_candidate, config)
else:
    final_candidate = mt_candidate

# Write SRT
write_candidate_srt(final_candidate, srt_path, config)

# Cleanup
Path(audio_path).unlink()
```

### Custom Processing

```python
from config import Config
from asr import FasterWhisperASR

# Custom configuration
config = Config()
config._config["asr"]["batch_size"] = 4  # Reduce for low memory

# Process with custom settings
asr = FasterWhisperASR(config)
segments = asr.transcribe_audio_to_segments("audio.wav")

# Filter short segments
segments = [s for s in segments if s.duration >= 1.0]

# Custom processing
for seg in segments:
    print(f"{seg.start:.1f}s: {seg.text}")
```

---

## Version Information

- **Pipeline Version:** 1.0
- **Python:** 3.9+
- **PyTorch:** 2.6+
- **Faster-Whisper:** 1.0+
- **Transformers:** 4.35+

---

## Support

For issues or questions:
1. Check this API documentation
2. Review the main README.md
3. Check logs in `logs/` directory
4. Run with `--log-level DEBUG` for detailed output

---

*Last Updated: 2025*
