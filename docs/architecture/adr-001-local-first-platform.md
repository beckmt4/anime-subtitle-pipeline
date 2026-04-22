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

All model inference (ASR, MT, LLM polish), media processing (ffmpeg), and
artifact storage (SQLite) run on the user's machine.  No data leaves the host
unless the user explicitly configures an external endpoint.

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

Use cloud ASR (e.g., Whisper API, AssemblyAI) and cloud MT (e.g., DeepL API).

**Rejected:** Privacy requirements make cloud processing unacceptable for the
primary use case.  Cloud APIs may be added as optional backends in future
packs, but local-only must always be the default path.

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

---

## Consequences

**Positive:**
- New language and domain support can be added without touching `core/`.
- All processing is reproducible and offline.
- Migration is low-risk and reviewable in small steps.

**Negative / trade-offs:**
- Abstract interfaces require more boilerplate than the current flat layout.
- Pack injection adds an indirection layer that must be understood by
  contributors.
- The gradual migration creates a period of dual ownership (root files + core
  shims) that must be tracked and cleaned up.

---

## References

- `docs/architecture/module-boundaries.md` — module ownership map and target
  layout.
- `specs/29-language-pack-interface.md` — language pack contract.
- `specs/30-domain-pack-interface.md` — domain pack contract.
- ADR-002 — anime + JAV pack model.
