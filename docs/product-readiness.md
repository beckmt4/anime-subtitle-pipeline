# Product Readiness — Subtitle Intelligence Platform

**Current classification: Advanced MVP / Alpha**

Good enough for: controlled local Japanese anime experiments, development, and
guided manual review.

Not yet good enough for: unattended library-scale production use, claimed
OCR-complete support, claimed true multi-language platform, or "set it and
trust the output" workflows.

---

## Release Gates

| Version | Label | Gate |
|---------|-------|------|
| **v0.1** | Japanese anime MVP | Japanese audio → SRT via ASR+MT+LLM, QC sidecar, policy routing, CI green |
| **v0.2** | Review + QC beta | Review queue, HTML UI, approve → SRT, translation memory, translation QC deterministic checks |
| **v0.3** | OCR beta | At least one reference OCR backend documented and tested, bitmap EN→SRT and JA→OCR→MT→SRT verified |
| **v0.4** | Library automation | Persistent SQLite queue, worker mode, retry/resume, recursive scan, status CLI |
| **v1.0** | Production local subtitle platform | All v0.x gates met, anime domain pack with real glossary fixtures, multi-language proof (≥2 source languages in tests), no stale docs, benchmark corpus with ≥20 fixture cases, CI enforces architecture guards |

---

## Capability Status Map

### Core pipeline

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| Japanese audio → ASR | **Implemented** | `tests/test_asr_candidate.py`, `tests/test_asr_quality_propagation.py` | Faster-Whisper, language-agnostic interface |
| Sidecar EN subtitles → SRT | **Implemented** | `tests/test_source_selection.py` | Direct demux, no MT |
| Embedded EN text subtitles → SRT | **Implemented** | `tests/test_source_selection.py`, `acceptance/38-embedded-en-detection.md` | |
| Japanese sidecar → MT → SRT | **Implemented** | `tests/test_orchestrator.py` | |
| Japanese embedded text → MT → SRT | **Implemented** | `tests/test_orchestrator.py` | |
| English audio → ASR → SRT | **Implemented** | `tests/test_orchestrator.py` | |
| Bitmap subtitle OCR → SRT | **Partial** | `acceptance/21-bitmap-ocr-cli-wiring.md` | CLI wired; no default backend; bring-your-own |
| Source-selection report | **Implemented** | `acceptance/52-explainable-source-selection-report.md` | Selection reason in every run metadata |
| Inspect-only / dry-run | **Implemented** | `acceptance/53-generate-inspect-only.md` | `--mode generate --inspect-only` |
| Candidate confidence scoring | **Implemented** | `acceptance/54-candidate-confidence-scoring.md` | ASR/OCR density, score |
| SRT overlap clamping | **Implemented** | `tests/test_srt_writer_overlap.py` | `min_gap_sec` enforced |
| Video muxing | **Implemented** | `tests/test_main_registry_integration.py` | ffmpeg optional mux step |

### Translation quality

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| MarianMT offline baseline | **Implemented** | `tests/test_translation_engine_selector.py` | Default engine |
| LLM-direct context-aware translation | **Implemented** | `acceptance/74-direct-llm-translation-engine.md` | `engine: llm_direct` |
| Hybrid (Marian + LLM refinement) | **Implemented** | `acceptance/75-translation-engine-selector.md` | `engine: hybrid` |
| Two-pass (literal → natural) | **Implemented** | `acceptance/two-pass-translation-workflow.md`, `tests/test_two_pass_translation.py` | Drift guard included |
| Live-action / adult profile | **Implemented** | `acceptance/77-live-action-adult-profile.md` | `dialogue_profile: live_action_adult` |
| Translation QC judge | **Implemented** | `acceptance/79-translation-qc-judge.md`, `tests/test_translation_qc.py` | Deterministic checks; LLM judge optional/disabled by default |
| Pack glossary / name enforcement | **Implemented** | `acceptance/134-pack-glossary-name-enforcement.md`, `tests/test_translation_glossary.py` | ja_en + anime/jav domain packs wired |
| Translation memory (approved corrections) | **Implemented** | `acceptance/136-translation-memory-approved-corrections.md`, `tests/test_translation_memory.py` | |
| Translation benchmark corpus | **Missing** | — | No fixture dataset; tracked in `specs/epics/epic-02-translation-quality.md` |
| Model / hardware comparison report | **Partial** | `acceptance/81-model-hardware-evaluation.md` | Framework documented; no validated corpus runs |
| LLMDirectTranslator language-agnostic prompts | **Partial** | — | Prompt still says "Japanese dialogue into English subtitles" (#642 in `core/mt/__init__.py`); tracked in `specs/epics/epic-02-translation-quality.md` |

### QC and policy

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| Subtitle QC (timing, blank, overlap) | **Implemented** | `tests/test_subtitle_qc.py` | `subtitle_qc.run_qc()` |
| Translation faithfulness QC | **Implemented** | `tests/test_translation_qc.py` | Length ratio, CJK leakage, keyword drift |
| QC sidecar JSON output | **Implemented** | `tests/test_orchestrator.py` | `*.en.qc.json` schema v2 |
| PolicyEngine routing | **Implemented** | `tests/test_asr_warning_routing.py` | score + ASR/OCR density + TQC status |
| Canonical failure taxonomy | **Implemented** | `tests/test_failure_taxonomy.py` | `core.quality.failure_taxonomy` |

### Human review

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| Review task generation rules | **Implemented** | `acceptance/82-review-task-generation-rules.md`, `tests/test_review_task_routing.py` | generate + benchmark routing |
| Review queue (list / render / approve) | **Implemented (MVP)** | `tests/test_review_workflow.py` | Backbone; UX not polished |
| Local HTML review UI | **Implemented (MVP)** | `core/review/workflow.py` | Side-by-side; no interactive JS |
| Approved SRT output | **Implemented (MVP)** | `tests/test_review_workflow.py` | Writes approved SRT |
| Translation memory from approved edits | **Implemented** | `acceptance/136-translation-memory-approved-corrections.md` | |
| Translation dataset export | **Implemented** | `acceptance/137-review-correction-dataset-exports.md`, `tests/test_translation_dataset_export.py` | |
| Review CLI polish (queue/render/approve/reject/export as subcommands) | **Partial** | — | Flags exist; UX needs hardening; tracked in `specs/epics/epic-04-review-workflow.md` |
| Review task deduplication / states | **Partial** | — | Tracked in `specs/epics/epic-04-review-workflow.md` |

### Artifact registry

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| SQLite artifact registry | **Implemented** | `tests/test_artifacts.py` | Media, runs, candidates, artifacts |
| Processing ledger | **Implemented** | `tests/test_artifacts.py` | Run history |
| Registry wiring in generate/benchmark | **Implemented** | `tests/test_pipeline_registry_wiring.py` | |
| DB auto-migration runner | **Implemented** | `acceptance/` (Phase 0) | Runs on startup |

### OCR

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| OCR backend interface + factory | **Implemented** | `core/ocr/__init__.py` | Abstract `OCRBackend` |
| OCR CLI wiring (generate/benchmark) | **Implemented** | `acceptance/21-bitmap-ocr-cli-wiring.md`, `tests/test_main_ocr_wiring.py` | |
| Default reference OCR backend | **Missing** | — | No default; bring-your-own only. Tracked in `specs/epics/epic-03-ocr-capability.md` |
| Bitmap extraction pipeline | **Missing** | — | No PGS/VobSub image extraction. Tracked in `specs/epics/epic-03-ocr-capability.md` |
| OCR test fixtures | **Missing** | — | No synthetic bitmap subtitle fixtures. Tracked in `specs/epics/epic-03-ocr-capability.md` |

### Batch / library automation

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| Directory batch runner | **Implemented** | `tests/test_batch_process.py` | Skip existing SRTs, watch mode |
| Persistent queue (SQLite-backed) | **Missing** | — | Tracked in `specs/epics/epic-05-library-automation.md` |
| Worker mode (run/watch/retry/resume) | **Missing** | — | Tracked in `specs/epics/epic-05-library-automation.md` |
| Status / reporting CLI | **Missing** | — | Tracked in `specs/epics/epic-05-library-automation.md` |
| Recursive library scanner with dedup | **Missing** | — | Tracked in `specs/epics/epic-05-library-automation.md` |

### Domain packs

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| Domain pack interface | **Implemented** | `acceptance/30-domain-pack-interface.md` | Abstract interface |
| Anime pack (structure + interface) | **Implemented** | `packs/domain/anime/` | Glossary/style files present |
| Anime pack (production glossary + fixtures) | **Partial** | — | Glossary files exist but content is thin; tracked in `specs/epics/epic-06-anime-domain-pack.md` |
| Anime honorific policy tested | **Missing** | — | Tracked in `specs/epics/epic-06-anime-domain-pack.md` |
| Signs / songs / OP-ED policy | **Missing** | — | Tracked in `specs/epics/epic-06-anime-domain-pack.md` |
| JAV pack (structure + interface) | **Implemented** | `packs/domain/jav/` | Privacy rules + adult register |
| JAV pack production validation | **Partial** | — | Tracked in `specs/epics/epic-06-anime-domain-pack.md` |

### Multi-language platform

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| Language-pack interface | **Implemented** | `acceptance/29-language-pack-interface.md` | `packs.language` API |
| ja_en reference pack | **Implemented** | `packs/language/ja_en/`, `tests/test_packs_language_ja_en.py` | Aliases, CJK filter, prompts, routing |
| Language-pack routing hooks in orchestrator | **Implemented** | `acceptance/language-pack-routing-hooks.md` | |
| en_en transcription pack | **Partial** | `packs/language/en_en/` | Structure only; no proven end-to-end test |
| ko_en / zh_en / es_en packs | **Structure only** | `packs/language/ko_en/`, `zh_en/`, `es_en/` | No MT content; not proven |
| Core modules free of hardcoded JA/EN prompts | **Partial** | — | `LLMDirectTranslator._build_prompt()` still says "Japanese dialogue into English subtitles"; tracked in `specs/epics/epic-07-multi-language-proof.md` |
| ≥2 non-Japanese workflows proven in tests | **Missing** | — | Tracked in `specs/epics/epic-07-multi-language-proof.md` |

### CI and architecture hygiene

| Capability | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| CI runs on every push/PR | **Implemented** | `.github/workflows/ci.yml` | |
| Lint covers core + packs + entrypoints | **Implemented** | `.github/workflows/ci.yml` | flake8 E9/F |
| Tests run without GPU / model downloads | **Implemented** | `conftest.py` stubs, `requirements-ci.txt` | |
| Architecture guard: no stale doc references | **Implemented** | `tests/test_architecture_guard.py` | Guards FILE_OVERVIEW + PROJECT_SUMMARY |
| Architecture guard: no root-shim imports in core/ | **Implemented** | `tests/test_architecture_guard.py` | |
| Acceptance-test index | **Implemented** | `acceptance/acceptance-test-index.md` | Maps epics to test evidence |
| Smoke tests (inspect-only, sidecar, ASR, MT, review) | **Partial** | Many covered in `tests/test_orchestrator.py`, `test_source_selection.py`, `test_review_workflow.py` | Explicit smoke test suite not consolidated; tracked in `specs/epics/epic-08-ci-hardening.md` |
| Release gates documented | **Implemented** | This document | See table above |

---

## Docs Accuracy

| Doc | Status |
|-----|--------|
| `docs/FILE_OVERVIEW.md` | ✅ Updated — reflects current `core/` architecture |
| `docs/PROJECT_SUMMARY.md` | ✅ Updated — reflects current architecture |
| `README.md` | ✅ Current — describes generate/benchmark/review modes and current config |
| `docs/BACKLOG.md` | ✅ Updated — completed items checked, new epics referenced |
| `docs/architecture/module-boundaries.md` | ✅ Current — describes target module map |
| `docs/QUICK_REFERENCE.md` | ✅ Updated — examples now import from `core.*` modules |
| `docs/API_DOCUMENTATION.md` | ✅ Updated — now documents current `core/` API surface only |
