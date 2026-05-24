# PROJECT SUMMARY: Anime Subtitle Pipeline

## Overview

A **local-first subtitle intelligence platform** for generating English subtitles
from Japanese anime, movies, and TV shows. All processing runs on-device; no cloud
APIs are required. The pipeline is structured for gradual expansion to additional
source languages and domain types.

> **Architecture note:** The original flat-file layout (`config.py`, `audio_utils.py`,
> `asr.py`, `mt.py`, `llm_polish.py`, `srt_writer.py`) has been fully migrated into
> the `core/` package hierarchy and retired to `attic/`. All new code imports from
> `core.*`.

## Data Flow

```
MKV/MP4
  │
  ├─→ Sidecar / embedded English subtitles ──────────────────────────────────┐
  ├─→ English audio → Faster-Whisper ASR ────────────────────────────────────┤
  ├─→ Sidecar / embedded Japanese subtitles → MT (→ LLM polish) ────────────┤
  ├─→ Bitmap Japanese subtitles → OCR → MT (→ LLM polish) ──────────────────┤
  └─→ Japanese audio → Faster-Whisper ASR → MT (→ LLM polish) ─────────────┤
                                                                              ▼
                                                               SubtitleCandidate(s)
                                                                              │
                                                              Subtitle QC + Translation QC
                                                                              │
                                                              PolicyEngine (pass/review/reject)
                                                                              │
                                                              SRT file  +  QC sidecar JSON
                                                                              │
                                                              Optional: ffmpeg mux into video
```

Source candidates carry full lineage metadata (engine, model, ASR quality,
OCR confidence, translation workflow, QC findings) through to the output artifact.

## Repository Structure

```
anime-subtitle-pipeline/
│
├── main.py                     # CLI entry point (generate/benchmark/subtitle/review modes)
├── batch_process.py            # Directory batch runner + watch mode
├── subtitle_qc.py              # Subtitle QC runner
├── translation_qc.py           # Translation faithfulness QC runner
├── config.yaml                 # Main YAML configuration (dev/prod profiles)
│
├── core/                       # Platform capability modules
│   ├── artifacts/              # SQLite artifact registry + processing ledger
│   ├── asr/                    # ASR backend: Faster-Whisper, language-agnostic interface
│   ├── benchmark/              # Benchmark engine: WER/BLEU/chrF candidate comparison
│   ├── extract/                # Audio extraction (ffmpeg), subtitle extraction utilities
│   ├── media/                  # Media inspection: streams, track metadata
│   ├── mt/                     # Translation: MarianMT, LLMDirect, Hybrid, engine selector
│   ├── ocr/                    # OCR backend interface + factory (bring-your-own backend)
│   ├── policy/                 # PolicyEngine: routing decisions (pass/review/reject)
│   ├── polish/                 # LLM polishing: Ollama-compatible, two-pass adaptation
│   ├── quality/                # Canonical QC failure taxonomy + code registry
│   ├── review/                 # Review task routing + review workflow (queue/approve/export)
│   ├── runtime/                # Orchestrator, config, tracing, batch runner
│   ├── subtitles/              # SRT writer, SubtitleCandidate model
│   └── translation/            # Translation memory, glossary enforcement, dataset export
│
├── packs/                      # Pluggable language and domain packs
│   ├── language/ja_en/         # Japanese→English (reference pack)
│   ├── language/en_en/         # English→English transcription
│   ├── language/ko_en/         # Korean→English (structure only)
│   ├── language/zh_en/         # Chinese→English (structure only)
│   ├── language/es_en/         # Spanish→English (structure only)
│   ├── domain/anime/           # Anime glossary, honorific policy, style
│   └── domain/jav/             # JAV privacy rules, adult register policy
│
├── tests/                      # 780+ pytest unit tests (no hardware required)
├── acceptance/                 # Per-issue acceptance checklists and test evidence
├── specs/                      # Pre-implementation design specs
├── docs/                       # Architecture docs, backlog, usage guides
├── fixtures/                   # Test fixtures (SRT, config stubs, etc.)
└── attic/                      # Retired code (do not import from here)
```

## Key Components

### 1. Configuration System (`core.runtime.config`)
- YAML-based configuration with `dev`/`prod` hardware profiles
- Profile-specific settings (quantization, batch sizes, model variants)
- Typed property accessors for all pipeline sections

### 2. Orchestrator (`core.runtime.orchestrator`)
- `run_generate()`: source-selection engine — discovers sidecar, embedded text,
  bitmap, and audio tracks; routes to best English output
- `run_benchmark()`: generate all candidate sources, compare with WER/BLEU/chrF
- Source-selection report included in metadata for every run
- Language-pack routing hooks for source→target direction

### 3. ASR Module (`core.asr`)
- Faster-Whisper with CTranslate2 backend
- Language-agnostic interface; language hint supplied by caller
- ASR quality diagnostics (no-speech probability, log prob, compression ratio)
- Warning density propagated through MT/polish to QC and routing

### 4. Translation Engine (`core.mt`)
- **MarianMT** (`engine: marian`): Helsinki-NLP offline baseline
- **LLM Direct** (`engine: llm_direct`): context-aware Ollama-compatible LLM
- **Hybrid** (`engine: hybrid`): Marian baseline fed to LLM for refinement
- Two-pass workflow (`workflow: literal_then_natural`): literal pass → drift-guarded
  natural adaptation
- Live-action/adult profile: explicit register preservation
- Engine, model, mode, dialogue profile, and fallback metadata recorded per candidate

### 5. LLM Polishing (`core.polish`)
- Ollama-compatible HTTP client with retry and fallback
- `adapt_candidate_from_literal()`: two-pass natural adaptation with drift guard
- Stock-phrase collapse guard: reverts to literal on hallucination collapse

### 6. SRT Writer (`core.subtitles`)
- Proper SRT timestamp formatting (HH:MM:SS,mmm)
- Adjacent cue gap clamping to prevent overlap
- Duration constraints (min/max)

### 7. QC and Policy (`subtitle_qc`, `translation_qc`, `core.policy`)
- Subtitle QC: blank cues, timing overlap, duration anomalies
- Translation QC: length ratio, CJK leakage, keyword drift, register changes
- PolicyEngine: score + ASR/OCR density + translation QC status → pass/review/reject
- QC sidecar JSON written alongside every SRT output

### 8. Review Workflow (`core.review`)
- Create review tasks from weak generate/benchmark outputs
- List review queue, render local HTML side-by-side UI
- Approve edits → write approved SRT → optionally store to translation memory
- Review task routing with stable reason codes

### 9. Artifact Registry (`core.artifacts`)
- SQLite-backed registry for media assets, pipeline runs, candidates, artifacts
- Processing ledger for run history
- Query API for artifact lookups

### 10. OCR (`core.ocr`)
- Abstract `OCRBackend` interface + factory
- Loads any `<module>:<Class>` backend from config
- Per-segment confidence; low-confidence density routes to review
- Default: `ocr.enabled: false` (bring-your-own backend for bitmap support)

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

# Use specific audio track
python main.py video.mkv --audio-track 1

# Enable debug logging
python main.py video.mkv --log-level DEBUG

# Inspect planned strategy without running models
python main.py video.mkv --mode generate --inspect-only

# Benchmark all sources
python main.py video.mkv --mode benchmark

# Review queue and approval
python main.py video.mkv --mode review --review-action queue
python main.py video.mkv --mode review --review-action render --task-id 12
python main.py video.mkv --mode review --review-action approve --task-id 12 --review-edits-json edits.json
```

## API Usage

```python
from core.runtime.config import Config, set_config
from core.extract.audio_utils import extract_audio_with_ffmpeg
from core.asr import FasterWhisperASR
from core.mt import translate_candidate
from core.polish import LLMPolisher
from core.subtitles import write_srt_file

# Load config
config = Config("config.yaml")
set_config(config)

# Extract audio
extract_audio_with_ffmpeg("video.mkv", "audio.wav")

# Transcribe
asr = FasterWhisperASR(config)
candidate = asr.transcribe_to_candidate("audio.wav", source="ja_audio_asr")

# Translate
candidate = translate_candidate(candidate, config)

# Polish (optional)
polisher = LLMPolisher(config)
candidate = polisher.polish_candidate(candidate)

# Write SRT
write_srt_file(candidate, "output.srt", config)
```

## Data Structures

### SubtitleCandidate
Core data structure passed through pipeline:
```python
@dataclass
class SubtitleCandidate:
    candidate_id: str        # Unique ID (e.g. "ja_audio_asr_mt_llm_a0")
    source: str              # Source type (e.g. "ja_audio_asr")
    segments: list           # List of Segment objects
    meta: dict               # Lineage metadata (engine, QC, scores, etc.)
```

### Segment
```python
@dataclass
class Segment:
    start: float             # Start time (seconds)
    end: float               # End time (seconds)
    text: str                # Subtitle text (language-agnostic)
    meta: dict               # Per-segment metadata (ASR quality, OCR confidence, etc.)
```

## Output Files

### SRT File (`outbox/video.en.srt`)
Standard SubRip format with English subtitles.

### QC Sidecar (`outbox/video.en.qc.json`)
Machine-readable QC report:
```json
{
  "schema_version": 2,
  "subtitle_qc": { "status": "pass", "findings": [] },
  "translation_qc": { "status": "warn", "score": 0.87, "findings": [] },
  "overall_qc_status": "warn"
}
```

### Muxed Video (optional, `outbox/video.en.mkv`)
Original video with embedded English subtitle track.

## Dependencies

### Python Packages
- `pyyaml` — Configuration
- `faster-whisper` — ASR
- `transformers` — MT models
- `torch` — Deep learning backend
- `requests` — HTTP client for LLM
- `sentencepiece`, `protobuf` — Tokenization

### External Tools
- `ffmpeg` — Audio/video processing
- `ollama` — Local LLM runtime (optional)

## Testing

```bash
# Run all non-integration tests (no GPU required)
pytest -v --tb=short -m "not integration"

# Run integration tests (requires GPU + models)
pytest -v --tb=short -m "integration"
```

See `tests/` for 780+ unit tests. See `acceptance/` for per-issue acceptance
evidence. See `docs/product-readiness.md` for current feature status.

## Design Decisions

1. **Local-only**: No data leaves the machine; no cloud API costs or privacy risk
2. **core/ package hierarchy**: Capability modules with clear ownership; no hardcoded language/domain rules in core
3. **Language packs**: Source/target language logic lives in `packs/language/`; core modules accept pack parameters
4. **Translation engine selector**: `marian` (offline baseline), `llm_direct` (context-aware LLM), `hybrid` (Marian + LLM refinement)
5. **Two-pass workflow**: Literal pass preserves meaning; natural adaptation with drift guard
6. **PolicyEngine**: Deterministic routing (pass/review/reject) based on score, ASR/OCR quality, translation QC
7. **Artifact registry**: SQLite-backed lineage tracking for every run
8. **YAML configuration**: Human-readable, supports comments, profile merging

## Roadmap

See `docs/BACKLOG.md` for the current ordered backlog and epic tracker.
See `docs/product-readiness.md` for capability status and release gates.

## License & Credits

- **Whisper**: MIT License (OpenAI)
- **MarianMT**: Apache 2.0 (Helsinki-NLP)
- **Qwen**: Apache 2.0 (Alibaba)
- **Pipeline Code**: Provided as-is for personal use
