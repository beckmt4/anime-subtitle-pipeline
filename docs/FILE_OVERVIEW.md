# Anime Subtitle Pipeline — File Overview

> **Note:** This document reflects the current `core/`-based architecture.
> The original flat-file layout (`config.py`, `audio_utils.py`, `asr.py`, `mt.py`,
> `llm_polish.py`, `srt_writer.py` as root modules) has been fully migrated into
> `core/` and retired to `attic/`. Do not import from those root names in new code.

## Repository Layout

```
anime-subtitle-pipeline/
│
├── main.py                     # CLI entry point (generate/benchmark/subtitle/review)
├── batch_process.py            # Directory batch runner + watch mode
├── subtitle_qc.py              # Subtitle QC runner (timing, blank, overlap checks)
├── translation_qc.py           # Translation faithfulness QC runner
├── config.yaml                 # Main YAML configuration (dev/prod profiles)
├── requirements.txt            # Full Python dependencies (GPU install)
├── requirements-ci.txt         # CI-only Python dependencies (no torch/whisper)
│
├── core/                       # Platform capability modules
│   ├── artifacts/              # SQLite artifact registry + processing ledger
│   ├── asr/                    # ASR backend interface + Faster-Whisper implementation
│   ├── benchmark/              # Benchmark engine (WER/BLEU/chrF, candidate comparison)
│   ├── extract/                # Audio extraction, subtitle extraction utilities
│   ├── media/                  # Media inspection (streams, track metadata)
│   ├── mt/                     # Translation backends: MarianMT, LLMDirect, Hybrid
│   ├── ocr/                    # OCR backend interface + factory
│   ├── policy/                 # PolicyEngine: routing decisions (pass/review/reject)
│   ├── polish/                 # LLM polishing backend (Ollama-compatible API)
│   ├── quality/                # Failure taxonomy, QC code registry
│   ├── review/                 # Review task routing, review workflow, approval
│   ├── runtime/                # Orchestrator, config loader, tracing, batch runner
│   ├── subtitles/              # SRT writer, subtitle models (SubtitleCandidate)
│   └── translation/            # Translation memory, glossary enforcement, dataset export
│
├── packs/                      # Language and domain plug-in packs
│   ├── language/
│   │   ├── ja_en/              # Japanese → English (reference pack)
│   │   ├── en_en/              # English → English (transcription-only)
│   │   ├── ko_en/              # Korean → English (pack structure, needs MT content)
│   │   ├── zh_en/              # Chinese → English (pack structure, needs MT content)
│   │   └── es_en/              # Spanish → English (pack structure, needs MT content)
│   └── domain/
│       ├── anime/              # Anime glossary, honorific style, sign policy
│       └── jav/                # JAV privacy rules, adult register policy
│
├── tests/                      # Pytest unit tests (780+ passing, no hardware required)
├── acceptance/                 # Acceptance checklists mapped to GitHub issues
├── specs/                      # Pre-implementation design specs
├── docs/                       # Architecture docs, backlog, usage guides
├── fixtures/                   # Test fixtures (SRT files, config stubs, etc.)
├── attic/                      # Retired code with explanation; do not import
└── scripts/                    # One-off helper scripts
```

## Runtime Entrypoints

| File | Purpose |
|------|---------|
| `main.py` | CLI: `--mode generate\|benchmark\|subtitle\|review` |
| `batch_process.py` | Batch-process a directory of media files; watch mode |
| `subtitle_qc.py` | Run subtitle QC checks against an SRT file |
| `translation_qc.py` | Run translation faithfulness QC against candidate pairs |
| `compare_srt.py` | Compare two SRT files (WER/BLEU/chrF) |
| `example_usage.py` | API usage examples |

## `core/` Module Summary

| Module | Owner capability | Key public API |
|--------|-----------------|----------------|
| `core.runtime.config` | Config loading, profile merging | `Config`, `set_config()` |
| `core.runtime.orchestrator` | Generate/benchmark flow control | `run_generate()`, `run_benchmark()` |
| `core.runtime.batch_process` | Batch/watch runner | `batch_process_directory()` |
| `core.runtime.tracing` | OpenTelemetry tracing | `get_tracer()` |
| `core.asr` | Speech-to-text backend | `FasterWhisperASR`, `ASRBackend` |
| `core.mt` | Translation engines | `MarianTranslator`, `LLMDirectTranslator`, `translate_candidate()` |
| `core.polish` | LLM polish / adaptation | `LLMPolisher`, `adapt_candidate_from_literal()` |
| `core.subtitles` | SRT writing, candidate models | `write_srt_file()`, `SubtitleCandidate` |
| `core.extract.audio_utils` | ffmpeg audio extraction + muxing | `extract_audio_with_ffmpeg()` |
| `core.extract.subtitle_utils` | Embedded/sidecar subtitle extraction | `extract_subtitle_track()` |
| `core.media` | Media file inspection | `MediaInfo`, `inspect_media()` |
| `core.ocr` | OCR backend interface + factory | `OCRBackend`, `create_backend()` |
| `core.benchmark` | Benchmark engine | `run_benchmark()` |
| `core.artifacts` | SQLite artifact registry | `ArtifactRegistry`, `ProcessingLedger` |
| `core.policy` | Routing policy enforcement | `PolicyEngine` |
| `core.review.routing` | Review-task creation rules | `route_generate_output()`, `route_benchmark_output()` |
| `core.review.workflow` | Review queue, HTML UI, approval | `list_review_queue()`, `render_review_ui()`, `approve_review_task()` |
| `core.translation.memory` | Translation memory (JSONL) | `TranslationMemory` |
| `core.translation.glossary` | Pack glossary enforcement | `load_glossary_for_candidate()` |
| `core.translation.dataset_export` | Export approved corrections | `export_translation_dataset()` |
| `core.quality.failure_taxonomy` | Canonical QC failure codes | `CANONICAL_CODES`, `normalize_code()` |

## `packs/` Module Summary

| Pack | Status | Description |
|------|--------|-------------|
| `packs.language.ja_en` | **Reference pack** | JA→EN: aliases, CJK filter, prompts, glossary, names, routing |
| `packs.language.en_en` | Pack structure only | EN→EN transcription; routing hook present |
| `packs.language.ko_en` | Pack structure only | KO→EN; no production MT content yet |
| `packs.language.zh_en` | Pack structure only | ZH→EN; no production MT content yet |
| `packs.language.es_en` | Pack structure only | ES→EN; no production MT content yet |
| `packs.domain.anime` | Alpha | Anime glossary + style policy |
| `packs.domain.jav` | Alpha | JAV privacy rules + adult register policy |

## Configuration

`config.yaml` drives all runtime behavior. Key sections:

| Section | Purpose |
|---------|---------|
| `runtime.profile` | Select `dev` or `prod` hardware preset |
| `asr` | Whisper model, compute type, quality thresholds |
| `mt` | MarianMT model settings |
| `translation` | Engine (`marian`/`llm_direct`/`hybrid`), workflow, dialogue profile |
| `translation_qc` | Faithfulness QC thresholds |
| `generate` | Source-preference policy for generate mode |
| `ocr` | OCR backend toggle + backend class path |
| `benchmark` | Candidate sources, engine list, pairwise flag |
| `policy.routing` | Score/ASR/OCR/QC routing thresholds |
| `llm` | Ollama endpoint, model, prompt styles |
| `paths` | inbox/outbox/logs/temp directories |

## Testing

All tests run without GPU or model downloads. Hardware-dependent tests are marked
`@pytest.mark.integration` and excluded in CI.

```bash
# Run all non-integration tests
pytest -v --tb=short -m "not integration"

# Run a specific file
pytest tests/test_config.py -v
```

See `acceptance/` for per-issue acceptance checklists and test evidence.

## Troubleshooting

| Issue | Check |
|-------|-------|
| Config errors | `config.yaml` syntax + `core.runtime.config` |
| Import errors | `requirements.txt`, `requirements-ci.txt` |
| ffmpeg issues | `core.extract.audio_utils`, PATH |
| CUDA OOM | `config.yaml` → `asr.dev.batch_size`, `compute_type` |
| LLM connection | `config.yaml` → `llm.base_url`, Ollama running |
| SRT formatting | `core.subtitles` → duration/gap settings |
| OCR not working | `config.yaml` → `ocr.enabled: true`, `ocr.backend` path |
