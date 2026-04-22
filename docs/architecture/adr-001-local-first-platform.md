# ADR-001: Local-First Platform Architecture

**Status:** Accepted  
**Issue:** #31  
**Date:** 2026-04-22  
**Deciders:** Platform team  
**Parent roadmap:** #15 — Subtitle Intelligence Platform master tracker

---

## Context

The project started as a single-purpose script for generating Japanese anime
subtitles using locally hosted ML models.  The goal is to scale it into a
reusable subtitle intelligence platform that supports multiple source
languages, target languages, domain types (anime, JAV, film, etc.), and
subtitle workflows — without sending any user data to external services.

Three architectural decisions underpin everything else:
1. **Local-first** — all processing happens on the user's hardware.
2. **Pack-based extension** — language and domain assumptions are injected via
   packs, not hardcoded into core modules.
3. **Gradual migration** — the working flat-file layout remains functional
   while the target `core/`/`packs/` structure is built alongside it.

---

## Decision

### 1. Local-first execution

**Definition:** Local-first means that every step of the subtitle pipeline
runs entirely on the user's machine using locally installed models and tools,
with no network dependency required for any core workflow.  The system must
produce identical results whether or not an internet connection is present.
Remote access is only permitted as an explicit, user-configured opt-in, and
must never be a prerequisite for running any workflow.

All model inference (ASR, MT, LLM polish), media inspection (ffmpeg),
OCR, benchmarking, artifact storage (SQLite), and review workflows run on the
user's machine.  No data leaves the host unless the user explicitly configures
an external endpoint.

#### Offline-capable workflows

The following workflows must be fully functional with no network access:

| Workflow | Runtime component | Offline requirement |
|---|---|---|
| Media inspection | `ffprobe` / `core/media` | Always offline |
| Audio extraction | `ffmpeg` / `core/extract` | Always offline |
| OCR | Local model (e.g., manga-ocr) / `core/ocr` | Always offline |
| ASR | Local model (e.g., Whisper) / `core/asr` | Always offline |
| Machine translation | Local model (e.g., NLLB, Fugumt) / `core/mt` | Always offline |
| LLM polishing | Local model (e.g., llama.cpp) / `core/polish` | Always offline |
| Subtitle writing | `core/subtitles` | Always offline |
| Benchmarking | `core/benchmark` | Always offline |
| Artifact storage | SQLite / `core/artifacts` | Always offline |
| Review workflow | Local diff / `core/review` | Always offline |

No step in the table above may block on a network call, authentication
token refresh, or remote model download at runtime.  Model weights must be
pre-downloaded and locally cached before the pipeline is invoked.

#### When remote access is allowed

Remote access is permitted **only** under all of the following conditions:

1. The user has **explicitly** set a non-local backend in `config.yaml` (e.g.,
   `asr.backend: openai_whisper_api`).
2. The remote endpoint is implemented as a named, swappable backend — not
   inlined into core logic.
3. The feature still works (at reduced quality or speed) when the remote
   endpoint is unavailable or unconfigured.
4. The remote call is documented as optional in both the spec and the
   configuration schema.

Examples of **allowed** remote opt-ins:
- Cloud ASR backend (`asr.backend: openai_whisper_api`) when user provides
  an API key in config.
- Remote MT backend (`mt.backend: deepl`) when user provides an API key.
- Telemetry or usage reporting (if added in future) with explicit opt-in flag.

Examples of **disallowed** remote calls:
- Downloading model weights at pipeline runtime without user consent.
- Phoning home for license verification, analytics, or crash reporting by
  default.
- Any `core/` module making an HTTP call without a user-configured remote
  backend.
- Implicit fallback from local to remote when local inference is slow or
  returns low confidence.

#### Optional remote endpoints: config and policy contract

Remote backends are represented in `config.yaml` as named string values on
the `backend` key of each module section.  The value `local` (or the absence
of a `backend` key) always means local execution.  Any other value is treated
as an optional integration and must be backed by an implementation in a
non-`core/` pack or adapter.

```yaml
# config.yaml — all defaults are local
asr:
  backend: local          # default; any other value is a remote opt-in
  model: base

mt:
  backend: local
  model: Helsinki-NLP/opus-mt-ja-en

polish:
  backend: local
  model: llama-3-8b-instruct.Q4_K_M.gguf
```

Policy rules enforced at review time:
- A PR may not change the default value of any `backend` key away from
  `local`.
- A PR that introduces a new remote backend must include: (a) a configuration
  schema entry, (b) a clear opt-in mechanism, (c) a test that the local path
  still passes when the remote backend is absent.
- `core/` modules must not import any HTTP client library directly.  Network
  I/O belongs in backend adapters, not in `core/`.

#### Privacy guarantees

Local-first implies the following privacy properties:

1. **No data exfiltration by default.**  Media files, extracted audio,
   intermediate transcripts, machine-translated segments, and polished
   subtitles never leave the host machine unless the user has configured a
   remote backend.
2. **No implicit model telemetry.**  Local model inference libraries
   (whisper.cpp, llama.cpp, CTranslate2, etc.) do not phone home.  If a
   library is added that has telemetry enabled by default, that telemetry
   must be disabled in the integration code.
3. **Artifacts stored locally.**  SQLite databases, SRT files, benchmark
   results, and log files are written to user-controlled paths only.
4. **No authentication tokens required for core operation.**  The pipeline
   must run without any API key, OAuth token, or cloud account credential.
5. **Sensitive content protection.**  Users processing content subject to
   copyright restrictions, personal privacy, or regional legal constraints
   can do so safely because nothing is transmitted off-device.

**Rationale:**
- Media content (especially anime fansubs and JAV) is privacy-sensitive.
- Users frequently process content that cannot be uploaded to cloud services
  due to copyright, personal privacy, or network constraints.
- Local inference is reproducible across runs without network dependency.

**Constraints introduced:**
- Hardware requirements must be documented (VRAM, RAM, storage).
- CPU-only fallback must remain functional, even if slower.
- No feature may be gated on a cloud API call.

### 2. Core modules are language-agnostic and domain-agnostic

All modules under `core/` must operate on abstract data types (`Segment`,
`SubtitleCandidate`, `MediaInfo`).  No `core` module may branch on a
hardcoded language code, language name, domain name, or model name.

Language-specific and domain-specific logic lives exclusively in `packs/`.

**Rationale:**
- Adding Chinese→English support must not require editing `core/mt`.
- Adding JAV domain support must not require editing `core/polish`.
- The decision rule for ambiguous cases: if the code would need to change
  when adding a new language or domain, it does not belong in `core`.

**Enforcement:**
- Code review checklist item: confirm no `core/` module imports from `packs/`.
- Architecture compliance check in `docs/ai-dev-policy.md`.

### 3. Gradual migration with backward-compatible shims

The current flat-file layout (`main.py`, `orchestrator.py`, `config.py`, etc.)
is **not broken** during migration.  New `core/` packages re-export from root
files until root files are fully migrated.

Migration phases (detailed in `docs/architecture/module-boundaries.md`):
- Phase 0: Architecture documented (this ADR + module-boundaries.md).
- Phase 1: Package skeleton + abstract interfaces created.
- Phase 2: Low-risk, no-dependency modules moved.
- Phase 3: Capability modules converted.
- Phase 4: Runtime and legacy glue removed.
- Phase 5: Unimplemented modules built (`core/ocr`, `core/artifacts`, etc.).

**Rationale:**
- A flag-day refactor of a working system carries high risk.
- The gradual approach allows PRs to be individually reviewed and reverted.
- Backward compatibility via shims means CI stays green throughout.

---

## Alternatives Considered

### A. Cloud-assisted pipeline

Use cloud ASR (e.g., Whisper API, AssemblyAI) and cloud MT (e.g., DeepL API)
as the default execution path.

**Rejected:** Privacy requirements make cloud processing unacceptable for the
primary use case.  Cloud APIs may be added as optional backends in future
packs, but local-only must always be the default path.  Additionally, a
cloud-first design would make the platform unusable in offline or
network-restricted environments.

### B. Single-file architecture

Keep everything in the flat root layout indefinitely; add language/domain
flags to existing modules.

**Rejected:** Flag-based branching in core modules is the pattern this
architecture is designed to prevent.  Each new language or domain adds
conditional branches that accumulate coupling.

### C. Plugin system with entry points

Use Python's `pkg_resources` / `importlib.metadata` entry points for pack
discovery.

**Deferred:** Entry-point-based discovery is a valid future extension.  For
Phase 1, explicit import paths (`packs.language.ja_en`, etc.) are simpler
and less error-prone.  Entry points can be layered on top once the pack
interface is stable.

### D. Hybrid default (local with automatic cloud fallback)

Run local models by default but silently fall back to cloud APIs when local
inference is slow, unavailable, or below a confidence threshold.

**Rejected:** Silent fallback violates the privacy guarantees that are the
primary motivation for local-first.  A user processing sensitive content
would have no way of knowing their data left the device.  Any remote fallback
must be explicit and user-initiated.

---

## Consequences

### Positive
- Users can run the full pipeline on air-gapped machines.
- Processing is deterministic and reproducible with no external rate limits
  or API quota concerns.
- Sensitive content (copyright-restricted, personally identifiable, or
  legally ambiguous) can be processed safely.
- New language and domain support can be added without touching `core/`.
- Migration is low-risk and reviewable in small steps.

### Negative / trade-offs

| Trade-off | Description | Mitigation |
|---|---|---|
| Hardware burden | Large ML models (Whisper large-v3, 7B+ LLMs) require substantial VRAM (8–24 GB) and RAM. | Document minimum and recommended specs in `README.md` and `docs/hardware-requirements.md`; provide smaller model tiers (Whisper base/small, 3B-param LLMs) for low-resource machines. |
| Initial setup friction | Users must download model weights before running the pipeline. | Provide a `setup.sh` / `install.ps1` that automates weight download and validates SHA-256 checksums against a pinned manifest. |
| Performance vs. cloud | Local inference on consumer hardware is slower than cloud-hosted accelerators. | Accept this trade-off explicitly; document expected throughput. Cloud backends can be added as optional packs. |
| Model update cadence | Local models do not auto-update; users must manually pull new weights. | Document model versioning and provide a clear upgrade path. |
| Operational complexity | Contributors must understand abstract interfaces and pack injection. | Enforce architecture rules at review; maintain `docs/architecture/module-boundaries.md` as the authoritative reference. |

### Future design implications

- Any new pipeline stage introduced after this ADR must default to a local
  backend.  A remote backend may be provided as an opt-in alternative, but
  never as the only option.
- Hardware requirement documentation (`README.md` / `HOW_TO_RUN.md`) must be
  updated whenever a new model tier is added.
- The `config.yaml` schema must include a `backend` key for every module that
  supports swappable implementations.
- A new `core/policy` module will enforce local-first constraints at runtime
  (e.g., refuse to run if a remote backend is set but no API key is present;
  warn if a required local model file is missing).

---

## References

- `docs/architecture/module-boundaries.md` — module ownership map and target
  layout.
- `specs/29-language-pack-interface.md` — language pack contract.
- `specs/30-domain-pack-interface.md` — domain pack contract.
- ADR-002 — anime + JAV pack model.
