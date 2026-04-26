# Module Boundaries — Subtitle Intelligence Platform

## 1. Purpose

This document defines the target module boundaries for the subtitle intelligence platform.

The pipeline started as a Japanese-only anime subtitle generator. The goal is to scale it into a local-first subtitle intelligence platform that can support multiple source languages, multiple target languages, multiple domain types (anime, JAV, film, etc.), multiple OCR/ASR/MT backends, and structured benchmarking — without hardcoding any of those decisions into a single undifferentiated codebase.

This document is the architecture reference for that transition. It does not define implementation — it defines ownership, so that future work lands in the right place and does not accumulate more coupling.

---

## 2. Issue Traceability

| Field | Value |
|---|---|
| **Direct issue** | [#28 — Define core platform module boundaries](https://github.com/beckmt4/anime-subtitle-pipeline/issues/28) |
| **Parent roadmap** | [#15 — Subtitle Intelligence Platform master tracker](https://github.com/beckmt4/anime-subtitle-pipeline/issues/15) |
| **Milestone** | M0 — Foundation and repo standards |
| **Status** | Foundation / reference architecture |
| **Scope** | Module ownership map, current-file classification, target package layout, migration phases |
| **Out of scope** | Implementation, backend selection, domain rule finalization, language pack content |

**How this supports #28:** This document is the primary deliverable required by #28. It defines 14 functional areas, maps every current file to a target module, provides a concrete target directory tree, and provides enough detail for each child issue (#29–#32, #17, #18, #19, #20) to reference it directly without re-deriving context.

**How this supports #15:** #15 tracks the full roadmap. Every milestone from M1 onward assumes a stable module boundary so that work lands in the right owner without creating new cross-cutting coupling. This document establishes that boundary agreement at M0.

---

## 3. Design Goals

- **Scale across languages and domains.** No module in `core` may hardcode Japanese, English, anime, or JAV assumptions. Those belong in packs.
- **Single capability owner per function.** Each platform capability — ASR, MT, polish, extraction, etc. — has exactly one owner module. Other modules call the owner's interface; they do not re-implement the capability.
- **Gradual migration.** The current flat file layout remains functional while the target package structure is built alongside it. No flag-day refactor.
- **Pack logic is injectable.** Core runtime accepts pack configuration; it does not switch on hardcoded domain names or language codes.
- **Reusable core.** Core modules should be useful to any subtitle workflow regardless of source language, target language, or domain type.
- **Separation of data contracts from implementation.** Shared data structures (Segment, SubtitleCandidate) are owned by core and must not embed language or domain assumptions.

---

## 4. Non-Goals

- **No implementation in this issue.** Module directories, `__init__.py` files, and interface definitions come in subsequent child issues.
- **No backend selection.** This document does not decide whether ASR will always use Faster-Whisper or whether MT will always use MarianMT. Backend selection is a pack or config concern.
- **No domain rule finalization.** Anime honorific policies, JAV privacy rules, and similar domain behaviors are not defined here.
- **No broad refactors.** Current files are not moved as part of this issue. The classification table (Section 9) records what should happen, not what has happened.

---

## 5. Core Principles

### What qualifies as `core`

A module belongs in `core` if:
- It provides a capability that any language or domain workflow could use.
- It operates on abstract interfaces (Segment, SubtitleCandidate, MediaInfo) rather than language-specific or domain-specific inputs.
- Removing it would break the platform regardless of which domain pack is active.

### What must not go in `core`

- Source-language-specific tokenization, segmentation heuristics, or reading-direction assumptions.
- Target-language-specific formatting rules.
- Domain-specific style policies (honorifics, adult content gates, genre-specific glossaries).
- Hardcoded model names or vendor-specific API shapes.
- CJK leak remediation (currently in `llm_polish.py`) — this is a Japanese-output quality quirk and belongs in a language pack.
- Language tag normalization tables (currently scattered across `media_inspect.py`, `orchestrator.py`, `audio_utils.py`) — these belong in the language pack interface (#29).

### How packs plug in

Packs supply configuration, prompt profiles, quality thresholds, model preferences, and preprocessing hooks. Core modules expose interfaces that accept pack-supplied parameters. Core never reads a domain name or language code to branch on embedded domain/language rules.

---

## 6. Target Module Map

### `core/media`

**Purpose:** Discover and inspect media files and their streams.

**Responsibilities:**
- Invoke ffprobe and parse the result into structured stream metadata.
- Classify streams by type (audio, text subtitle, bitmap subtitle).
- Provide language-code normalization that is protocol-level (ISO-639 mapping), not language-pack-specific.
- Select preferred audio or subtitle tracks given a priority list supplied by the caller.

**Inputs:** video file path, optional priority lists.
**Outputs:** `MediaInfo`, `AudioStream`, `SubtitleStream`.

**Belongs here:** `inspect_media`, `MediaInfo`, `AudioStream`, `SubtitleStream`, `choose_audio_track`, ISO-639 language code normalization.

**Does not belong here:** Language-pack-specific tag aliases (e.g., the Japanese alias set in `orchestrator._LANG_ALIASES`), domain-specific stream selection heuristics.

**Dependencies:** none within core.

---

### `core/extract`

**Purpose:** Extract raw audio or subtitle data from video containers.

**Responsibilities:**
- Extract audio tracks to WAV (ffmpeg wrapper). Parameterize sample rate and channel count rather than hardcoding Whisper defaults.
- Demux embedded text subtitle tracks (SRT, ASS, SSA) to file and parse them into `SubtitleCandidate`.
- Mux an SRT back into a video container.
- Define clean boundaries so OCR-required (bitmap) tracks are handed off to `core/ocr`, not silently rejected.

**Inputs:** video file path, stream index, `MediaInfo`, output directory.
**Outputs:** WAV file path (audio), `SubtitleCandidate` (subtitle), muxed video path.

**Belongs here:** `extract_audio_with_ffmpeg`, `extract_subtitle_track`, `parse_srt`, `mux_subtitle_to_video`.

**Does not belong here:** ASR (audio→text), OCR (bitmap→text), subtitle formatting constraints. Bitmap subtitle tracks should be detected here and routed to `core/ocr`; extraction itself is not OCR.

**Dependencies:** `core/media` (MediaInfo, SubtitleStream), `core/subtitles` (Segment, SubtitleCandidate).

---

### `core/ocr`

**Purpose:** Convert bitmap subtitle tracks (PGS, VOBSUB, XSUB) to text.

**Responsibilities:**
- Accept a bitmap subtitle stream (or extracted image frames) and return text with timestamps.
- Define the backend abstraction so the OCR engine is swappable.
- Score extraction confidence and expose it for downstream quality routing.
- Route low-confidence results to `core/review`.

**Inputs:** video path + subtitle stream index, or pre-extracted image frames.
**Outputs:** `SubtitleCandidate` with confidence metadata.

**Belongs here:** OCR engine abstraction, confidence scoring, bitmap detection (currently raising RuntimeError in `subtitle_utils.py`).

**Does not belong here:** Language-specific OCR model selection, domain-specific post-processing. Those go in packs.

**Dependencies:** `core/extract` (bitmap track detection), `core/subtitles` (data structures), `core/review` (low-confidence routing).

**Current state:** Not implemented. `subtitle_utils.extract_subtitle_track` raises `RuntimeError` for bitmap codecs. This is the correct stopgap; it must not be silently swallowed.

---

### `core/asr`

**Purpose:** Convert audio to timestamped text segments.

**Responsibilities:**
- Define the ASR backend interface (accepts audio path + language hint, returns `SubtitleCandidate`).
- Manage model lifecycle (load, transcribe, unload).
- Provide batch and one-shot interfaces.
- Expose confidence per segment for downstream routing.

**Inputs:** WAV file path, language code.
**Outputs:** `SubtitleCandidate` with language metadata.

**Belongs here:** `FasterWhisperASR`, `build_candidate_from_segments`, `transcribe_audio_to_candidate`, `BatchASR`. The abstract ASR interface that future backends will implement.

**Does not belong here:** Language-specific segmentation post-processing, domain-specific vocabulary hints. The language code passed to the ASR backend comes from the caller (pack or runtime), not from hardcoded logic inside `core/asr`.

**Dependencies:** `core/subtitles` (Segment, SubtitleCandidate), `core/runtime` (Config).

**Current state:** `asr.py` implements this but carries a legacy `Segment` type (5 fields: start, end, text_ja, text_en_raw, text_en_final) alongside the generic `models.Segment` (3 fields). The legacy type must be retired (see item #7 of static review).

---

### `core/mt`

**Purpose:** Translate subtitle text from one language to another.

**Responsibilities:**
- Define the MT backend interface (accepts `SubtitleCandidate` in source language, returns `SubtitleCandidate` in target language).
- Handle batching to avoid memory blowout (currently a known issue: ~900 segments can consume 48 GB RAM if not chunked).
- Manage model lifecycle.

**Inputs:** `SubtitleCandidate` (source language).
**Outputs:** `SubtitleCandidate` (target language).

**Belongs here:** `MarianTranslator`, `translate_candidate_jp_to_en` (to be renamed to a language-agnostic form), `BatchTranslator`.

**Does not belong here:** The ja→en direction assumption encoded in the function name `translate_candidate_jp_to_en`. The target module uses a direction-agnostic interface; language pack configuration supplies source and target language codes.

**Dependencies:** `core/subtitles`, `core/runtime` (Config).

---

### `core/polish`

**Purpose:** Improve translated subtitle quality using a local LLM.

**Responsibilities:**
- Define the polish backend interface (accepts `SubtitleCandidate`, returns improved `SubtitleCandidate`).
- Manage Ollama-compatible HTTP API requests and retries.
- Apply whitespace/constraint normalization after polish.
- Expose the connection check so callers can gate on LLM availability.

**Inputs:** `SubtitleCandidate`, style hint from pack or config.
**Outputs:** Improved `SubtitleCandidate`.

**Belongs here:** `LLMPolisher`, `polish_candidate_with_llm`, `enforce_constraints_on_candidate`, `BatchPolisher`.

**Does not belong here:** CJK character leak detection and `_recover_leading_english` — these are artifacts of Japanese-source + qwen2.5:7b output behavior and belong in a Japanese language pack or in model-specific configuration. The core polish module should either pass output through a pack-supplied post-processor hook or treat CJK filtering as an injectable validator, not hardcode it.

**Dependencies:** `core/subtitles`, `core/runtime` (Config).

---

### `core/subtitles`

**Purpose:** Own the shared subtitle data model and SRT formatting.

**Responsibilities:**
- Define `Segment` and `SubtitleCandidate` — the platform's primary data contracts.
- Format `SubtitleCandidate` to SRT with timing, duration, and line-length constraints.
- Parse SRT files back to `SubtitleCandidate` (for benchmarking and review input).
- Enforce subtitle timing constraints (min/max duration, segment splitting).

**Inputs:** `SubtitleCandidate`, config constraints.
**Outputs:** `.srt` file, or `SubtitleCandidate` parsed from `.srt`.

**Belongs here:** `models.Segment`, `models.SubtitleCandidate`, `SRTWriter`, `write_candidate_srt`, `read_srt_file`, `format_timestamp_srt`, `split_text_by_punctuation`, `split_into_lines`.

**Does not belong here:** Language-specific line-splitting heuristics (e.g., Japanese line break rules differ from English). Those belong in a language pack's formatting policy. Domain-specific character limits (manga vs anime vs film) belong in domain packs.

**Dependencies:** none within core.

---

### `core/benchmark`

**Purpose:** Measure subtitle quality by comparing candidates to a reference.

**Responsibilities:**
- Discover all subtitle/audio sources for a given media file.
- Generate candidates from each source using the appropriate pipeline path.
- Select a reference candidate based on configurable policy.
- Align segments temporally and compute quality metrics (WER, BLEU, chrF).
- Persist comparison results to JSON for later review.
- Generate HTML diff reports.

**Inputs:** video file, config, optional reference SRT.
**Outputs:** benchmark result JSON, metrics dict, comparison reports.

**Belongs here:** `run_benchmark`, `find_all_tracks_by_language`, `select_reference_candidate`, `align_segments`, `compute_metrics`.

**Does not belong here:** Domain-specific benchmark fixtures (anime-specific test cases), language-specific metric weighting. Those go in packs.

**Dependencies:** `core/media`, `core/extract`, `core/asr`, `core/mt`, `core/polish`, `core/subtitles`, `core/artifacts`.

---

### `core/artifacts`

**Purpose:** Persist and retrieve pipeline outputs, candidates, benchmark runs, and review tasks.

**Responsibilities:**
- Maintain a processing ledger that tracks which files have been processed and with what outcomes.
- Store and version subtitle candidates.
- Record benchmark run results for regression comparison.
- Support re-processing with recorded reason.

**Inputs:** pipeline outputs, metadata dicts.
**Outputs:** stored artifacts, query results.

**Belongs here:** SQLite schema (Issue #18), artifact registry, candidate versioning, benchmark run storage, processing ledger.

**Does not belong here:** Application-level business logic, quality policies.

**Current state:** Not implemented. Outputs currently land as flat files in `outbox/` and `logs/`. This module is the target for Issue #18.

**Dependencies:** `core/subtitles` (data structures), `core/runtime` (Config, paths).

---

### `core/policy`

**Purpose:** Centralize configurable quality thresholds, routing decisions, and content gates.

**Responsibilities:**
- Define when a low-confidence result should be routed to review vs. passed through.
- Define what constitutes a "pass" on a benchmark comparison.
- Accept pack-supplied threshold overrides.
- Gate adult-content workflows (requires explicit opt-in; default off).

**Inputs:** confidence scores, benchmark metrics, domain pack config.
**Outputs:** routing decisions (pass/review/reject).

**Belongs here:** Threshold definitions, routing logic, domain pack threshold injection.

**Does not belong here:** Domain-specific default values (those live in the domain pack and are injected). Language-specific quality heuristics.

**Current state:** Not implemented as a module. Policy currently lives as hardcoded thresholds scattered across `orchestrator.py` (strategy selection), `llm_polish.py` (CJK thresholds), and `config.yaml` (min/max duration, LLM flags).

**Dependencies:** `core/artifacts`, `core/runtime`.

---

### `core/review`

**Purpose:** Manage human review tasks for low-confidence or flagged subtitle candidates.

**Responsibilities:**
- Maintain a review queue.
- Define the review task model (segment-level flagging, side-by-side comparison, approval state).
- Expose an interface for a local UI to consume review tasks.
- Record review history.

**Inputs:** flagged `SubtitleCandidate`, policy routing decisions.
**Outputs:** approved or edited `SubtitleCandidate`, review records.

**Belongs here:** Review task model, queue management, segment editing interface, approval workflow.

**Does not belong here:** The review UI itself (that's a separate layer on top), domain-specific review protocols (those are pack-injected).

**Current state:** Not implemented. Target for Issue #22.

**Dependencies:** `core/artifacts`, `core/policy`, `core/subtitles`.

---

### `core/runtime`

**Purpose:** Orchestrate the full pipeline; manage config, execution strategy, and worker execution.

**Responsibilities:**
- Load and validate configuration.
- Implement the source-selection decision tree (currently in `orchestrator.py`).
- Provide the CLI entry point.
- Run the worker/queue model for batch processing.
- Accept pack-supplied workflow overrides and inject them into the pipeline.
- Own the tracing/observability setup.

**Inputs:** CLI args, config file, media file paths, pack config.
**Outputs:** pipeline execution results, artifact references.

**Belongs here:** `Config`, `run_generate`, source selection logic, `main()`, `batch_process`, `setup_tracing`, `start_span`.

**Does not belong here:** Individual capability implementations (those belong in their respective modules). Language-specific strategy choices (those are injected by language packs). Domain-specific preprocessing (injected by domain packs).

**Current state:** Split across `main.py`, `orchestrator.py`, `config.py`, `tracing.py`, and `batch_process.py`. The global config singleton is a known coupling point.

**Dependencies:** all other core modules (runtime is the integration layer).

---

## 7. Core vs Non-Core Guidance

| Belongs in `core` | Belongs in `packs/language/...` | Belongs in `packs/domain/...` |
|---|---|---|
| `Segment`, `SubtitleCandidate` data structures | Language-bound model defaults (e.g., `opus-mt-ja-en`) | Subtitle style profiles (anime, film, broadcast) |
| SRT formatting engine | Source-language VAD/segmentation post-processing | Honorific handling rules |
| ffprobe stream inspection | Target-language line-break heuristics | OP/ED skip/treatment policy |
| ffmpeg audio extraction and subtitle mux | CJK leak remediation (Japanese-output artifact) | Signs/on-screen text handling policy |
| ASR backend abstraction | Language code alias sets | Domain-specific glossaries |
| MT backend abstraction | ISO-639 label normalization for that language | Review threshold overrides per domain |
| LLM polish backend abstraction | LLM prompt templates for source→target | Privacy/logging redaction policy (JAV) |
| Temporal segment alignment | Reading-direction assumptions | Content gate / adult opt-in |
| WER/BLEU/chrF computation | Language-specific confidence scoring thresholds | Domain benchmark fixtures |
| Quality threshold routing | | Naming/output file conventions per domain |
| Review task model | | Domain-specific metadata tagging |
| Artifact registry | | |
| Config loading | | |

**Decision rule for ambiguous cases:** If the code would need to change when adding a new language (e.g., Chinese, Spanish), it does not belong in core. If it would need to change when adding a new domain (e.g., documentary), it does not belong in core. Only if it is genuinely invariant across languages and domains does it belong in core.

---

## 8. Target Repo/Package Layout

```
anime-subtitle-pipeline/
│
├── core/
│   ├── media/          # stream inspection, source discovery
│   ├── extract/        # audio extraction, subtitle demux, mux
│   ├── ocr/            # bitmap subtitle → text (not yet implemented)
│   ├── asr/            # speech → text backend abstraction
│   ├── mt/             # translation backend abstraction
│   ├── polish/         # LLM quality improvement backend
│   ├── subtitles/      # Segment, SubtitleCandidate, SRT formatting
│   ├── benchmark/      # candidate comparison, metrics
│   ├── artifacts/      # processing ledger, artifact storage (Issue #18)
│   ├── policy/         # quality thresholds, routing decisions
│   ├── review/         # review task model, queue (Issue #22)
│   └── runtime/        # config, orchestration, CLI, tracing
│
├── packs/
│   ├── language/
│   │   └── ja_en/      # Japanese source → English target pack
│   │       ├── aliases.py          # language tag normalization
│   │       ├── prompts.py          # LLM prompt templates
│   │       ├── cjk_filter.py       # CJK leak remediation
│   │       └── config.yaml         # model defaults, thresholds
│   └── domain/
│       ├── anime/      # anime style pack (Issue #23)
│       │   ├── style.py            # honorifics, OP/ED, signs policy
│       │   ├── glossary.yaml       # anime terminology
│       │   └── config.yaml         # review thresholds, source preferences
│       └── jav/        # JAV domain pack (Issue #24)
│           ├── privacy.py          # logging redaction, content gates
│           └── config.yaml         # privacy policy, adult opt-in flag
│
├── docs/
│   └── architecture/
│       └── module-boundaries.md   # this document
│
├── specs/              # feature specs (per Issue #17 dev workflow)
├── prompts/            # prompt templates (per Issue #17)
├── fixtures/           # test fixtures (per Issue #17)
├── acceptance/         # acceptance criteria definitions (per Issue #17)
│
├── tests/              # test suite (currently flat in root)
│
│   # Current flat layout — to be migrated gradually
├── main.py
├── orchestrator.py
├── config.py
├── models.py
├── media_inspect.py
├── audio_utils.py
├── asr.py
├── mt.py
├── llm_polish.py
├── srt_writer.py
├── subtitle_utils.py
├── benchmark.py
├── compare_core.py
├── tracing.py
├── batch_process.py
└── config.yaml
```

The flat root files remain functional during migration. The `core/` and `packs/` trees are built alongside them. Once a module is migrated, the root file becomes a thin shim or is removed.

---

## 9. Current Repo Mapping

| Current file | Current responsibility | Target module | Disposition | Notes |
|---|---|---|---|---|
| `main.py` | CLI entry point, legacy 6-step pipeline, mode dispatch | `core/runtime` | move later | Contains both the legacy `process_video()` path and the new `run_generate()` dispatch. Legacy path should be removed after `run_generate` covers all cases. |
| `orchestrator.py` | Source-selection decision tree, strategy execution | `core/runtime` | move later | The decision tree logic is correct; the language aliases embedded in `_LANG_ALIASES` should move to language packs. |
| `config.py` | YAML loader, profile merge, typed accessors, global singleton | `core/runtime` | move later | Global singleton is a coupling problem. Target is dependency injection. |
| `models.py` | `Segment`, `SubtitleCandidate` data structures | `core/subtitles` | move later | Clean module; no coupling issues. Primary blocker is the shadow `asr.Segment` type. |
| `media_inspect.py` | ffprobe wrapper, stream metadata, language normalization | `core/media` | move later | `LANG_MAP` normalization table should be extended to support the language pack interface (#29). |
| `audio_utils.py` | Audio extraction, mux, track listing, legacy Japanese track finder | `core/extract` | move later | `find_japanese_audio_track()` is dead code — superseded by `media_inspect.choose_audio_track()`. Mark for removal. |
| `asr.py` | Faster-Whisper wrapper, legacy `Segment` type | `core/asr` | move later | Legacy `asr.Segment` (5-field) must be retired; migrate callers to `models.Segment`. Lazy model loading pattern needs cleanup. |
| `mt.py` | MarianMT wrapper, batch translation, legacy Segment API | `core/mt` | move later | `translate_candidate_jp_to_en` name encodes language direction — rename to direction-agnostic form. Batch chunking fix (48 GB issue) is correct and must be preserved. |
| `llm_polish.py` | Ollama API client, CJK leak remediation, constraint enforcement | `core/polish` | move later | CJK leak detection (`_CJK_RE`, `_recover_leading_english`) is language-pack logic (Japanese output artifact from qwen2.5:7b). Move to `packs/language/ja_en/cjk_filter.py` as an injectable hook. |
| `srt_writer.py` | SRT formatting, timing constraints, segment splitting | `core/subtitles` | move later | `write_srt_file()` (legacy Segment API) can be removed once `asr.Segment` is retired. Temporary Segment creation inside `write_candidate_srt()` is an unnecessary translation layer. |
| `subtitle_utils.py` | Embedded subtitle demux, SRT parse | `core/extract` | move later | Bitmap RuntimeError is correct behavior today; OCR routing should replace it when `core/ocr` is built. |
| `benchmark.py` | Multi-source candidate generation, reference selection, JSON output | `core/benchmark` | move later | Solid implementation. `find_all_tracks_by_language` naming is good but should move alongside `compare_core`. |
| `compare_core.py` | Temporal alignment, WER/BLEU/chrF computation | `core/benchmark` | move later | Clean; no coupling issues. Moves together with `benchmark.py`. |
| `tracing.py` | OpenTelemetry setup, span context manager | `core/runtime` | move later | Disabled by default (`TRACING_ENABLED=1` required). No-op path is clean. |
| `batch_process.py` | Batch inbox processing, watch mode | `core/runtime` | move later | Currently imports `process_video` from `main.py` — should switch to `run_generate` before migration. |
| `benchmark_configs.py` | Config sweep, timing + quality measurement | `core/benchmark` | keep (experimental) | Used for hyperparameter tuning. Classify as tooling, not shipped platform code. |
| `evaluate_subtitles.py` | Reference-based quality evaluation | `core/benchmark` | keep | Likely wraps `compare_core`; move with benchmark module. |
| `build_dataset.py` | Training dataset construction | unassigned tooling | keep | Out of platform scope for now; does not belong in `core`. |
| `extract_training_data.py` | Training data extraction | unassigned tooling | keep | Same as above. |
| `compare_subtitles.py` | Legacy subtitle comparison | — | replace | Superseded by `compare_core + benchmark.py`. Dead code candidate. |
| `compare_srt.py` | Legacy SRT comparison | — | replace | Same as above. Verify no active callers before removing. |
| `example_usage.py` | Usage examples | — | keep (dev only) | Not shipped; not in test suite. |
| `debug_test.py` | Manual debug script | — | keep (dev only) | Same as above. |
| `asr.Segment` (within asr.py) | Legacy 5-field segment with text_ja/text_en fields | retire | replace | Migrate all callers to `models.Segment`. This is static review item #7. |
| `audio_utils.find_japanese_audio_track()` | Legacy Japanese audio search | retire | replace | Superseded by `media_inspect.choose_audio_track()`. |
| `main.process_video()` | Legacy linear pipeline | retire | replace | Superseded by `orchestrator.run_generate()`. Remove once CLI coverage is confirmed. |

---

## 10. Migration Guidance

Migration happens in phases. Each phase is a separate issue or set of issues. No phase requires a flag day.

### Phase 0 — Document only (this issue)
- Architecture document committed.
- No files moved.
- No interfaces changed.
- Deliverable: `docs/architecture/module-boundaries.md`.
- **Status: ✅ Complete**

### Phase 1 — Establish package skeleton and interfaces
- Create `core/` and `packs/` directory trees with `__init__.py` files.
- Define abstract base interfaces for ASR, MT, polish, extract, OCR backends.
- Define the language pack interface (Issue #29) and domain pack interface (Issue #30).
- Write ADR-001 (local-first platform) and ADR-002 (anime + JAV pack model).
- No capability code moved yet; interfaces define the contracts.
- **Status: ✅ Complete**

Deliverables committed:
- `core/` — 12-module skeleton with abstract base classes and root shims.
- `packs/language/ja_en/` — reference language pack (`aliases`, `prompts`, `cjk_filter`).
- `packs/domain/anime/` — anime style pack with `style.get_style_config()`.
- `packs/domain/jav/` — JAV privacy pack with content gate and metadata redaction.
- `docs/architecture/adr-001-local-first-platform.md`.
- `docs/architecture/adr-002-pack-model.md`.
- `specs/29-language-pack-interface.md` and `specs/30-domain-pack-interface.md`.
- `acceptance/29-language-pack-interface.md`, `acceptance/30-domain-pack-interface.md`,
  and `acceptance/15-platform-rearchitecture.md`.
- `tests/test_packs_language_ja_en.py` (27 tests) and `tests/test_packs_domain.py` (18 tests).

### Phase 2 — Move low-risk, no-dependency modules
Modules with no local imports move first:
- `models.py` → `core/subtitles/`
- `media_inspect.py` → `core/media/`
- `tracing.py` → `core/runtime/`
- `compare_core.py` → `core/benchmark/`

Each move is a single PR: new location, root shim re-exports for backward compatibility, tests updated.

### Phase 3 — Convert capability modules
- `audio_utils.py` → `core/extract/` (remove `find_japanese_audio_track` at this point)
- `subtitle_utils.py` → `core/extract/`
- `srt_writer.py` → `core/subtitles/`
- `asr.py` → `core/asr/` (retire legacy `asr.Segment` at this point — static review #7)
- `mt.py` → `core/mt/` (rename direction-specific functions)
- `llm_polish.py` → `core/polish/` (CJK filter already extracted to `packs/language/ja_en/cjk_filter.py`)
- `benchmark.py` → `core/benchmark/`

### Phase 4 — Convert runtime and remove legacy glue
- `config.py` → `core/runtime/` with dependency injection refactor
- `orchestrator.py` → `core/runtime/` (move `_LANG_ALIASES` to `packs/language/ja_en/aliases.py`)
- `batch_process.py` → `core/runtime/` (switch to `run_generate`)
- `main.py` → slim entry point that imports from `core/runtime`
- Remove `main.process_video()` (legacy pipeline)
- Remove root shims from Phase 2/3

### Phase 5 — Build unimplemented modules
After migration, build net-new modules:
- `core/ocr/` (Issue #21) — interface stub exists; implementation needed
- `core/artifacts/` (Issue #18) — stub exists; SQLite implementation needed
- `core/policy/` — stub exists; threshold routing implementation needed
- `core/review/` (Issue #22) — stub exists; queue implementation needed
- Populate `packs/domain/anime/glossary.yaml` (Issue #23)
- Complete `packs/domain/jav/` privacy audit (Issue #24)

---

## 11. Acceptance Criteria Mapping

This section maps directly to the acceptance criteria stated in Issue #28 and the parent EPIC.

| Acceptance criterion | Status | Where addressed |
|---|---|---|
| Architecture doc exists | ✅ Done | This document, committed at `docs/architecture/module-boundaries.md` |
| ADR for local-first platform | ✅ Done | `docs/architecture/adr-001-local-first-platform.md` |
| ADR for anime + JAV pack model | ✅ Done | `docs/architecture/adr-002-pack-model.md` |
| Module/pack interfaces defined | ✅ Done (Phase 1) | Abstract base classes in `core/asr`, `core/mt`, `core/polish`, `core/ocr`; specs in `specs/29-*`, `specs/30-*` |
| Repo structure documented | ✅ Done | Section 8 (target package layout), Section 9 (current file mapping) |
| Each capability has a single defined owner | ✅ Done | Section 6: 12 modules defined, each with exclusive ownership of its capability |
| Shared platform services distinguished from pack-specific logic | ✅ Done | Section 7 (core vs non-core table); `packs/language/ja_en/` and `packs/domain/` hold pack logic |
| Target repo/package layout included | ✅ Done | Section 8; `core/` and `packs/` skeleton committed |
| Language pack interface defined | ✅ Done | `packs/language/ja_en/` reference pack; `specs/29-language-pack-interface.md`; `acceptance/29-language-pack-interface.md` |
| Domain pack interface defined | ✅ Done | `packs/domain/anime/` and `packs/domain/jav/`; `specs/30-domain-pack-interface.md`; `acceptance/30-domain-pack-interface.md` |
| Future growth path explicit | ✅ Done | ADR-002 Growth Path section; Phase 2–5 guidance above |
| Design explicit enough for child issues to reference | ✅ Done | Each module entry in Section 6 is directly referenceable; Section 9 maps every current file |

---

## 12. Open Questions and Follow-on Issues

**Resolved in Phase 1:**
- **#29** — Language pack interface: ✅ implemented in `packs/language/ja_en/`.
- **#30** — Domain pack interface: ✅ implemented in `packs/domain/anime/` and `packs/domain/jav/`.
- **#31** — ADR: local-first platform: ✅ `docs/architecture/adr-001-local-first-platform.md`.
- **#32** — ADR: anime + JAV pack model: ✅ `docs/architecture/adr-002-pack-model.md`.

**Open / near-term (Phase 2/3):**
- Runtime interface cleanup: define Config injection pattern to replace global singleton.
- Extraction split: separate audio extraction from subtitle mux into distinct sub-modules within `core/extract`.
- Legacy retirement: `asr.Segment`, `find_japanese_audio_track()`, `process_video()` — tracked as static review item #7.
- **#17** — AI dev workflow: Reference Section 8 for where `specs/`, `prompts/`, `fixtures/`, `acceptance/` directories land.
- **#18** — Persistent state and artifact registry: Reference Section 6 (`core/artifacts`) for ownership and scope.

**Open questions to resolve before Phase 3:**
- Should language pack aliases live in `config.yaml` or in Python pack files? Decision: Python pack files (as implemented in `packs/language/ja_en/aliases.py`); runtime config can reference pack ID.
- Is `ConcurrentPolisher` in `llm_polish.py` used in production? **Resolved: deleted** (commit 675bd7b) — it was dead code with no callers and skipped safety guards.
- The benchmark HTML renderer referenced in Issue #20 — does it live in `core/benchmark` or as a separate reporting layer?
- `build_dataset.py` and `extract_training_data.py` — are these platform tooling or external scripts? Clarify before Phase 3.
