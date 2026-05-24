# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all unit tests (excludes integration tests requiring hardware/services)
pytest -v --tb=short -m "not integration"

# Run a single test file or function
pytest tests/test_config.py -v
pytest tests/test_config.py::test_profile_merge -v

# Lint (subset matching CI)
flake8 core/media/__init__.py core/benchmark/compare_core.py core/runtime/config.py core/subtitles/models.py \
  core/runtime/orchestrator.py core/polish/__init__.py core/subtitles/srt_writer.py \
  core/extract/audio_utils.py core/extract/subtitle_utils.py core/asr/__init__.py core/mt/__init__.py \
  core/runtime/tracing.py core/runtime/batch_process.py core/benchmark/__init__.py \
  --select=E9,F --extend-ignore=F401,F841 --exclude venv

# Run the pipeline
python main.py <video_file> [--mode generate|subtitle|benchmark|inspect-only] \
  [--profile dev|prod] [--no-llm] [--no-mux]
```

**Style:** max-line-length 100, max-doc-length 120 (see `setup.cfg`).

## Architecture

This is a **local-first** subtitle generation pipeline for Japanese anime. All processing runs on-device; no cloud APIs are used.

### Data flow

```
MKV/MP4 → ffmpeg (audio extraction) → WAV
→ Faster-Whisper (ASR) → Japanese segments
→ Helsinki-NLP MarianMT (MT) → raw English
→ Qwen via Ollama (optional LLM polish) → polished English
→ SRT file → ffmpeg (mux into video)
```

### Module layout

The repo is mid-migration to `core/` + `packs/`. Runtime entrypoints remain at the root.

**Root-level runtime entrypoints/shims:**
- `main.py` — CLI entry point
- `orchestrator.py` — top-level generate/benchmark flow control
- `config.py` — YAML config loader with dev/prod profile merging
- `batch_process.py` — batch run wrapper
- `subtitle_qc.py`, `translation_qc.py` — QC and quality gates

**`core/` (new modular layer):**
- `core/artifacts/` — SQLite registry for media assets, streams, pipeline runs, subtitle candidates
- `core/policy/` — runtime enforcement of local-first constraints
- `core/asr/`, `core/mt/`, `core/polish/`, `core/subtitles/`, `core/media/` — capability modules (migration targets)
- `core/benchmark/` — benchmarking engine
- `core/extract/` — audio/subtitle/OCR extraction
- `core/review/` — review workflow infrastructure

**`packs/` (pluggable language/domain logic):**
- `packs/language/ja_en/` — Japanese→English aliases, CJK filters, prompts
- `packs/domain/anime/` — anime glossary and style rules
- `packs/domain/jav/` — JAV domain privacy rules

### Configuration

`config.yaml` drives all runtime behavior via two profiles:
- `dev` — RTX A3000 6GB, int8_float16 quantization, 7B LLM
- `prod` — RTX 4090 24GB, float16, 14B+ LLM

Profile is selected via `runtime.profile` in `config.yaml` or `--profile` CLI flag.

### Testing

Heavy ML/GPU packages are stubbed in `conftest.py` so the full test suite runs CPU-only in CI. `requirements-ci.txt` omits torch/whisper/transformers. Tests using real hardware are marked `@pytest.mark.integration` and excluded in CI.

### Architecture decisions

Key design decisions are captured in `docs/architecture/`:
- `adr-001-local-first-platform.md` — why no cloud APIs
- `adr-002-pack-model.md` — why language/domain logic lives in packs, not core
- `module-boundaries.md` — migration phases and ownership map
